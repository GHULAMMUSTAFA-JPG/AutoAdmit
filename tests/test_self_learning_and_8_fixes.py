"""Comprehensive tests for all 8 root-cause fixes + Self-Learning Domain Playbooks + Step 2 Canary Gate."""

import asyncio
import json
import httpx
import pytest

from app.core.config import settings
from app.core.llm_router import LLMEndpoint, LLMRouter
from app.core.types import ErrorCode, StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.schemas.entities import DomainPlaybookDoc, PageSnapshotDoc, UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.phase2_extractor import (
    Phase2ExtractorService,
    decode_obfuscated_email,
    extract_photo_url_from_markdown,
    is_valid_email,
    is_valid_photo_url,
    verify_professor_grounding,
)
from app.services.phase2_scraper import (
    detect_inline_table_roster,
    extract_profile_urls_with_audit,
    is_plausible_person_name,
)
from app.services.runner import PipelineRunner, is_canary_sentinel_mismatch
from app.services.site_tree_builder import (
    SiteTreeBuilder,
    detect_cms_fingerprint,
    matches_department_scope,
)


def test_roster_context_grounding_email_and_photo_validators():
    # 1. 'roster_context' accepted with verified faculty roster URL (HFUT / USTC pattern)
    ok_hfut, reason = verify_professor_grounding(
        markdown="# 张旭东\n计算机与信息学院教师，研究方向：人工智能。",
        breadcrumb="首页 > 师资队伍",
        name_quote="张旭东",
        supervisor_quote="roster_context",
        source_roster_url="http://ci.hfut.edu.cn/szdw/js.htm",
    )
    assert ok_hfut is True, reason

    # 2. 'roster_context' accepted when bio contains valid academic rank even if roster URL is generic
    ok_rank, reason2 = verify_professor_grounding(
        markdown="# 肖俊斌\n职称：副教授，研究方向：网络安全。",
        breadcrumb="",
        name_quote="肖俊斌",
        supervisor_quote="roster_context",
        source_roster_url="https://example.edu.cn/generic.htm",
    )
    assert ok_rank is True, reason2

    # 3. Unverified hallucinated name still strictly rejected
    ok_bad, bad_reason = verify_professor_grounding(
        markdown="# 张旭东\n教授",
        breadcrumb="",
        name_quote="不存在的教授",
        supervisor_quote="roster_context",
        source_roster_url="http://ci.hfut.edu.cn/szdw/js.htm",
    )
    assert ok_bad is False
    assert "not found verbatim" in bad_reason

    # 4. Strict email validation rejects USTC 256-char RSA hex & truncated _t@ / _cdu@
    rsa_hex = "0781a630c90b863f" * 16 + "@ustc.edu.cn"
    assert is_valid_email(rsa_hex) is False
    assert is_valid_email("_t@swufe.edu.cn") is False
    assert is_valid_email("_cdu@163.com") is False
    assert decode_obfuscated_email("_t@swufe.edu.cn") == ""
    assert decode_obfuscated_email("zhangwei at cs dot ustc dot edu dot cn") == "zhangwei@cs.ustc.edu.cn"

    # 5. Photo icon filter rejects search.png, logo, icon, .svg while keeping real portraits
    assert is_valid_photo_url("https://it.swufe.edu.cn/picture/search.png") is False
    assert is_valid_photo_url("https://cs.ahu.edu.cn/images/logo.svg") is False
    assert is_valid_photo_url("https://ci.hfut.edu.cn/__local/A/B/portrait.jpg") is True
    md = "![search](/picture/search.png)\n![prof](/__local/prof_zhang.jpg)"
    assert extract_photo_url_from_markdown(md, "https://it.swufe.edu.cn/info/1.htm").endswith("/__local/prof_zhang.jpg")


def test_parent_hop_scope_prefixed_names_inline_table_and_noise_denylist():
    # 1. Parent-hop scope inheritance for ahpu.edu.cn/jsjyxxgc/5476/list.htm
    child_html = "<html><head><title>硕士生导师</title></head><body><div>导师列表</div></body></html>"
    assert matches_department_scope(
        "https://www.ahpu.edu.cn/jsjyxxgc/5476/list.htm",
        child_html,
        "Computer Science",
        inherited_dept_url="https://www.ahpu.edu.cn/jsjyxxgc/",
    ) is True

    # 2. Prefix stripping for ahtcm.edu.cn ('导师简介——董长续') + noise rejection (xygz/byly, publications/)
    assert is_plausible_person_name("导师简介——董长续") is True
    assert is_plausible_person_name("导师简介—阚红星") is True
    assert is_plausible_person_name("教师简介：张伟") is True

    roster_html = """
    <html><body><main>
      <a href="/info/1001/1.htm">导师简介——董长续</a>
      <a href="/info/1001/2.htm">导师简介—阚红星</a>
      <a href="/info/1001/3.htm">教师简介：王明</a>
      <a href="/xygz/byly.htm">张伟</a>
      <a href="/publications/202212-shan-cover-image/">李强</a>
    </main></body></html>
    """
    urls, audit = extract_profile_urls_with_audit(roster_html, "https://xxgc.ahtcm.edu.cn/xkzy1/dsjj.htm", root_domain="ahtcm.edu.cn")
    assert len(urls) == 3
    assert all("byly" not in u and "publications/" not in u for u in urls)
    assert audit["dropped_breakdown"]["admin_slug"] >= 2

    # 3. Archetype B: Single-page inline table roster (aufe.edu.cn)
    inline_html = """
    <html><head><title>硕士生导师 - 计算机与信息工程学院</title></head>
    <body><table>
      <tr><td>张三</td><td>教授</td><td>硕士生导师</td></tr>
      <tr><td>李四</td><td>副教授</td><td>硕士生导师</td></tr>
      <tr><td>王五</td><td>教授</td><td>博士生导师</td></tr>
    </table></body></html>
    """
    is_inline, hits = detect_inline_table_roster(inline_html, "https://jxxy.aufe.edu.cn/14342/list.htm")
    assert is_inline is True
    assert hits >= 4
    assert detect_cms_fingerprint("https://jxxy.aufe.edu.cn/14342/list.htm", inline_html) == "webplus_list"


@pytest.mark.asyncio
async def test_waf_412_recovery_anti_hallucination_playbook_and_telemetry():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_8fixes")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        # Mock LLM returning one hallucinated URL, one self-loop URL, and one valid candidate URL
        def llm_handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content.decode("utf-8"))
            txt = body["messages"][-1]["content"]
            if "Current page: https://www.ahu.edu.cn" in txt:
                content = json.dumps({
                    "branches": [
                        {"label": "Hallucinated", "url": "https://www.ahu.edu.cn/fake/hallucinated.htm", "zone": "BODY"},
                        {"label": "SelfLoop", "url": "https://www.ahu.edu.cn", "zone": "NAV"},
                        {"label": "计算机科学与技术学院", "url": "https://cs.ahu.edu.cn/szdw/js.htm", "zone": "NAV"},
                    ]
                })
            else:
                content = json.dumps({"is_valid_dept_faculty_roster": True, "roster_degree_scope": "all", "reason": "ok"})
            return httpx.Response(200, json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 220, "completion_tokens": 45, "total_tokens": 265},
            })

        # HTTPX returns 412 WAF on cs.ahu.edu.cn; Playwright resolves it to 200 with real faculty roster
        def web_handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u.endswith("/robots.txt"):
                return httpx.Response(404)
            if u.rstrip("/") == "https://www.ahu.edu.cn":
                return httpx.Response(200, text="<html><nav><a href='https://cs.ahu.edu.cn/szdw/js.htm'>计算机科学与技术学院</a></nav></html>")
            if "cs.ahu.edu.cn" in u:
                return httpx.Response(412, text="<script>document.cookie='waf=1'</script>")
            return httpx.Response(404)

        async def mock_pw(url: str) -> tuple[int, str, str]:
            html = """
            <html><head><title>师资队伍 - 计算机科学与技术学院</title></head>
            <body><main>
              <a href='/info/1001/1.htm'>张伟 教授</a>
              <a href='/info/1001/2.htm'>李敏 副教授</a>
              <a href='/info/1001/3.htm'>王磊 教授</a>
              <p>教授 副教授 博导 硕导 教授</p>
            </main></body></html>
            """
            return 200, url, html

        router = LLMRouter(
            colab=LLMEndpoint("colab_qwen", "https://colab.mock/v1", "k", "Qwen/Qwen3-8B-AWQ", tier=1, auth_header="X-API-Key"),
            primary=LLMEndpoint("primary", "", "", "", tier=2),
            backup=LLMEndpoint("backup", "", "", "", tier=3),
            backoff_delays=(0.0, 0.0),
            trace_repo=repo,
        )
        builder = SiteTreeBuilder(
            repo=repo,
            admin=AdminConfig(enable_playwright=True, enable_serper=False, enable_colab_bridge=True),
            router=router,
            transport=httpx.MockTransport(lambda r: llm_handler(r) if "colab.mock" in str(r.url) else web_handler(r)),
            playwright_fetcher=mock_pw,
        )
        res = await builder.build_and_find_roster("ahu.edu.cn", "Computer Science", "masters")
        assert res.ok is True
        assert res.data["roster_url"] == "https://cs.ahu.edu.cn/szdw/js.htm"

        # Verify Self-Learning Playbook recorded requires_playwright_waf_reload=True & verified_roster_urls
        pb = await repo.get_domain_playbook("ahu.edu.cn")
        assert pb is not None
        assert pb.requires_playwright_waf_reload is True
        assert "https://cs.ahu.edu.cn/szdw/js.htm" in pb.verified_roster_urls

        # Verify Issue 8 telemetry: markdown_chars > 0 in http_fetch_traces & system_prompt_tokens > 0 in api_call_traces
        fetches = await repo.list_http_fetch_traces(domain="ahu.edu.cn")
        assert any(f.markdown_chars > 0 for f in fetches)
        traces = await repo.list_api_call_traces(limit=20)
        assert any(t.system_prompt_tokens > 0 for t in traces)
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_8fixes")
        await mgr.close()


@pytest.mark.asyncio
async def test_step2_canary_gate_halts_batch_on_sentinel_mismatch():
    assert is_canary_sentinel_mismatch(ErrorCode.GROUNDING_FAILED, "supervisor_evidence_quote 'roster_context' not found") is True
    assert is_canary_sentinel_mismatch(ErrorCode.GROUNDING_FAILED, "name_evidence_quote 'abc' not found") is False

    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_canary")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        extract_calls = 0

        class StubP1:
            async def discover(self, dom, dept, deg):
                return StepResult.success(
                    UniversityDeptDoc(
                        domain=dom, department=dept, degree=deg,
                        department_url=f"https://cs.{dom}", faculty_roster_url=f"https://cs.{dom}/szdw.htm",
                        winning_strategy="TREE_DFS", status="COMPLETE",
                    )
                )

        class StubScraper:
            async def crawl_roster_urls(self, roster_url):
                return StepResult.success({
                    "profile_urls": [f"https://cs.test.edu.cn/p{i}.htm" for i in range(1, 6)],
                    "roster_title": "师资队伍",
                    "roster_mode": "BIO_LINKS",
                })

            async def fetch_and_snapshot_profile(self, url, dom):
                return StepResult.success(PageSnapshotDoc(url=url, domain=dom, markdown="# 张三", breadcrumb="", sha256="x"))

        class FailingCanaryExtractor:
            async def extract_from_snapshot(self, snap, **kwargs):
                nonlocal extract_calls
                extract_calls += 1
                return StepResult.fail(ErrorCode.GROUNDING_FAILED, "supervisor_evidence_quote 'roster_context' not found verbatim")

        runner = PipelineRunner(repo, StubP1(), StubScraper(), FailingCanaryExtractor(), admin=AdminConfig(max_concurrent_universities=1))
        job = await runner.run_job(domains=["test.edu.cn"], department="Computer Science", degree="masters", job_id="job_canary_test")
        assert job.status == "COMPLETED"
        assert extract_calls == 1  # Canary halted after Professor #1 instead of wasting 5 calls!
        assert "canary_validation_alert" in job.scorecard
        assert job.scorecard["canary_validation_alert"]["error_code"] == "CANARY_VALIDATION_ALERT"
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_canary")
        await mgr.close()
