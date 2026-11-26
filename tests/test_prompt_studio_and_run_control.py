"""Tests for Part A (5 post-run fixes) & Part B (Qwen Prompt Studio, Hard-Refresh Active Job, Frozen Run Archives, Stop Pipeline)."""

import io
import zipfile
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.job_control import freeze_run_archive
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import JobDoc, ProfessorDoc
from app.schemas.filters import AdminConfig
from app.services.phase2_extractor import filter_negated_degrees
from app.services.phase2_scraper import (
    Phase2ScraperService,
    extract_profile_urls_with_audit,
    is_same_root_domain,
)
from app.services.site_tree_builder import extract_3zone_links_with_meta


def test_part_a_chinese_degrees_malformed_url_and_webplus_date_bios():
    # 1. Bilingual Chinese degree normalization (fixes ahpu.edu.cn raw=['硕士'])
    assert filter_negated_degrees("张伟 副教授 硕士生导师", "", ["硕士"]) == ["masters"]
    assert filter_negated_degrees("李明 教授 博士生导师", "", ["博士生导师", "硕士"]) == ["phd", "masters"]
    assert filter_negated_degrees("非博导，仅招收硕士", "", ["博士", "硕士"]) == ["masters"]

    # 2. Malformed Chinese hostname (fixes ahjzu.edu.cn ValueError crash)
    assert is_same_root_domain("http://这条招新推文到底怎么发？", "ahjzu.edu.cn") is False
    bad_html = """
    <html><body><nav>
      <a href="http://这条招新推文到底怎么发？">招新推文</a>
      <a href="https://cs.ahjzu.edu.cn/szdw.htm">师资队伍</a>
    </nav></body></html>
    """
    zones, _ = extract_3zone_links_with_meta(bad_html, "https://www.ahjzu.edu.cn", "ahjzu.edu.cn", department="Computer Science")
    assert len(zones["NAV"]) == 1
    assert zones["NAV"][0]["url"] == "https://cs.ahjzu.edu.cn/szdw.htm"

    # 3. WebPlus date-path professor bio kept when anchor is person name, dropped when news headline
    webplus_html = """
    <html><body><main>
      <a href="/2023/0512/c14342a101/page.htm">张伟</a>
      <a href="/2023/0512/c14342a102/page.htm">李敏</a>
      <a href="/2024/0901/c14342a999/page.htm">学院召开2024年秋季工作会议</a>
    </main></body></html>
    """
    urls, audit = extract_profile_urls_with_audit(webplus_html, "https://jxxy.aufe.edu.cn/14342/list.htm", root_domain="aufe.edu.cn")
    assert len(urls) == 2
    assert audit["dropped_breakdown"]["news_date"] == 1


@pytest.mark.asyncio
async def test_part_a_profile_snapshot_playwright_fallback():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_pw_prof")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def fail_httpx(req: httpx.Request) -> httpx.Response:
            return httpx.Response(412, text="<script>waf()</script>")

        async def mock_pw(url: str) -> tuple[int, str, str]:
            return 200, url, "<html><head><title>张伟-安徽农业大学</title></head><body><h1>张伟</h1><p>教授 博导</p></body></html>"

        scraper = Phase2ScraperService(
            repo=repo,
            admin=AdminConfig(enable_playwright=True),
            transport=httpx.MockTransport(fail_httpx),
            playwright_fetcher=mock_pw,
            per_domain_delay=0.0,
        )
        res = await scraper.fetch_and_snapshot_profile("https://xzxy.ahau.edu.cn/info/1001/1.htm", "ahau.edu.cn")
        assert res.ok is True
        assert "张伟" in res.data.markdown
        traces = await repo.list_http_fetch_traces(domain="ahau.edu.cn")
        assert any(t.engine == "playwright" and t.markdown_chars > 0 for t in traces)
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_pw_prof")
        await mgr.close()


@pytest.mark.asyncio
async def test_part_b_prompt_studio_active_job_stop_and_frozen_run_zip():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_studio")
    db = await mgr.connect()
    await db["prompt_versions"].delete_many({})
    await db["jobs"].delete_many({})
    await db["run_archives"].delete_many({})
    await db["professors"].delete_many({})
    app = create_app(manager=mgr)
    repo = Repository(db)
    app.state.repo = repo
    app.state.admin_config = AdminConfig()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Prompt Studio auto-seeds v1, saves v2 preserving v1, and restores v1
            r0 = await client.get("/api/v1/prompts")
            assert r0.status_code == 200
            prompts = r0.json()["prompts"]
            ext_item = next(p for p in prompts if p["prompt_key"] == "phase2_extractor")
            v1_id = ext_item["active"]["version_id"]
            assert ext_item["active"]["version"] == 1

            r1 = await client.post(
                "/api/v1/prompts/phase2_extractor",
                json={
                    "system_prompt": "Custom Qwen System Prompt v2",
                    "user_prompt_template": "Custom v2 extractor template for {sent_md} and {breadcrumb}",
                    "note": "Pasted custom prompt v2",
                },
            )
            assert r1.status_code == 200
            body1 = r1.json()
            assert body1["saved"]["version"] == 2
            assert body1["saved"]["is_active"] is True
            assert len(body1["versions"]) == 2
            assert any(v["version"] == 1 and v["is_active"] is False for v in body1["versions"])

            r2 = await client.post(f"/api/v1/prompts/phase2_extractor/activate/{v1_id}")
            assert r2.status_code == 200
            assert r2.json()["activated"]["version"] == 1
            assert r2.json()["activated"]["is_active"] is True

            # 2. Active Job re-attach (hard refresh), Stop Pipeline, and Frozen Per-Run ZIP Archive
            await repo.upsert_job(JobDoc(
                job_id="job_old_run",
                status="COMPLETED",
                request={"regions": ["Anhui"]},
                target_domains=["ustc.edu.cn"],
                completed_domains=["ustc.edu.cn"],
                scorecard={"mode": "TREE_EXTRACT", "total_verified_professors": 1},
            ))
            await repo.upsert_professor(ProfessorDoc(
                canonical_profile_url="https://faculty.ustc.edu.cn/p1.htm",
                university_domain="ustc.edu.cn",
                department="Computer Science",
                source_roster_url="https://faculty.ustc.edu.cn/list.jsp",
                name="张伟",
                name_en="Wei Zhang",
                title="教授",
                title_en="Professor",
                email="zw@ustc.edu.cn",
                email_status="FOUND",
                degree_eligibility=["phd"],
                name_evidence_quote="张伟",
                supervisor_evidence_quote="教授",
            ))
            await freeze_run_archive(repo, "job_old_run")

            await repo.upsert_job(JobDoc(
                job_id="job_live_now",
                status="RUNNING",
                request={"regions": ["Beijing"]},
                target_domains=["tsinghua.edu.cn"],
                completed_domains=[],
                scorecard={"mode": "TREE_ONLY"},
            ))

            ra = await client.get("/api/v1/jobs/active")
            assert ra.status_code == 200
            assert ra.json()["active"] is True
            assert ra.json()["job"]["job_id"] == "job_live_now"

            # Stop running job cleanly
            rs = await client.post("/api/v1/jobs/job_live_now/stop")
            assert rs.status_code == 200
            assert rs.json()["status"] == "STOPPED"
            assert (await client.get("/api/v1/jobs/active")).json()["active"] is False

            # History lists both runs with frozen archives
            rh = await client.get("/api/v1/jobs/history")
            assert rh.status_code == 200
            hist = rh.json()
            assert any(h["job_id"] == "job_old_run" and h["has_frozen_archive"] is True for h in hist)

            # Downloading old run ZIP returns its frozen snapshot even after newer run existed
            rz = await client.get("/api/v1/export/run-logs-zip?job_id=job_old_run")
            assert rz.status_code == 200
            zf = zipfile.ZipFile(io.BytesIO(rz.content))
            assert "job_summary.json" in zf.namelist()
            assert "professors.json" in zf.namelist()
            assert "张伟" in zf.read("professors.json").decode("utf-8")
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_studio")
        await mgr.close()
