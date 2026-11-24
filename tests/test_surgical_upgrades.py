"""Unit & integration tests for surgical upgrades:
- .nav/#nav/.menu extraction (excluding breadcrumbs/pagination) + nav_type tagging (SEMANTIC_NAV vs DIV_BASED_NAV)
- Carousel stripping, HOME/SCHOOLS_DIR/DEPT_HOME/index URL gate rejection, org-name rejection, non-CS/exchange blocking
- Comma-separated BACKUP_LLM_MODEL 503 failover + api_call_traces logging + /api/v1/analytics/*
- POST /api/v1/trees/extract Step 2 batch execution
- Bilingual professor extraction (name_en, title_en, research_areas_en, absolute photo_url) + CSV/JSON exports
"""

import json
import httpx
import pytest

from app.core.config import settings
from app.core.llm_router import LLMEndpoint, LLMRouter
from app.core.logging import get_job_log_path
from app.core.types import StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import (
    PageSnapshotDoc,
    ProfessorDoc,
    UniversitySiteTreeDoc,
    VerifiedRosterEntry,
)
from app.schemas.filters import AdminConfig
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import (
    extract_profile_urls,
    is_plausible_person_name,
    verify_roster_html,
)
from app.services.site_tree_builder import (
    extract_3zone_links_with_meta,
    is_blocked_academic_link,
)
from scripts.seed_universities import seed_universities


def test_div_nav_vs_semantic_nav_and_exclusions():
    div_html = """
    <html><body>
      <div class="breadcrumb"><a href="/home">Home</a></div>
      <div class="pagination"><a href="/page/2">Next</a></div>
      <div id="nav" class="menu">
        <a href="https://cs.test.edu.cn/szdw.htm">师资队伍</a>
        <a href="https://stuex.test.edu.cn/en/">Exchange Portal</a>
        <a href="https://shmc.test.edu.cn/lyys/list.htm">医学院</a>
      </div>
      <div class="swiper">
        <a href="https://cs.test.edu.cn/info/9/promo.htm">张伟</a>
      </div>
      <main>
        <a href="https://cs.test.edu.cn/jsml.htm">教师名录</a>
      </main>
    </body></html>
    """
    zones, nav_type = extract_3zone_links_with_meta(
        div_html, "https://cs.test.edu.cn/", "test.edu.cn", department="Computer Science"
    )
    assert nav_type == "DIV_BASED_NAV"
    nav_urls = [x["url"] for x in zones["NAV"]]
    assert "https://cs.test.edu.cn/szdw.htm" in nav_urls
    # Blocked subdomains and non-CS colleges excluded
    assert all("stuex." not in u for u in nav_urls)
    assert all("shmc." not in u for u in nav_urls)
    # Carousel links stripped from BODY
    body_urls = [x["url"] for x in zones["BODY"]]
    assert "https://cs.test.edu.cn/info/9/promo.htm" not in body_urls
    assert "https://cs.test.edu.cn/jsml.htm" in body_urls

    sem_html = """<html><body><header><nav><a href="https://www.test.edu.cn/yxsz.htm">院系设置</a></nav></header></body></html>"""
    _, nav_type2 = extract_3zone_links_with_meta(sem_html, "https://www.test.edu.cn/", "test.edu.cn")
    assert nav_type2 == "SEMANTIC_NAV"

    assert is_blocked_academic_link("https://stuex.nju.edu.cn/en/cs", "CS", "Computer Science") is True
    assert is_blocked_academic_link("https://shmc.fudan.edu.cn/lyys/list.htm", "医学院", "Computer Science") is True
    assert is_blocked_academic_link("https://cs.tsinghua.edu.cn/szdw.htm", "计算机系", "Computer Science") is False


def test_roster_gate_rejects_homepages_carousels_and_org_names():
    assert is_plausible_person_name("张伟") is True
    assert is_plausible_person_name("John Smith") is True
    assert is_plausible_person_name("计算机学院") is False
    assert is_plausible_person_name("人工智能研究院") is False
    assert is_plausible_person_name("School of Computer Science") is False
    assert is_plausible_person_name("AI Research Institute") is False

    # Carousel-only names must be stripped and rejected
    carousel_html = """
    <html><body>
      <div class="carousel">
        <a href="https://cs.hust.edu.cn/info/1/zw.htm">张伟</a>
        <a href="https://cs.hust.edu.cn/info/2/lm.htm">李明</a>
        <a href="https://cs.hust.edu.cn/info/3/wf.htm">王芳</a>
      </div>
    </body></html>
    """
    assert extract_profile_urls(carousel_html, "https://cs.hust.edu.cn/szdw.htm", root_domain="hust.edu.cn") == []
    ok_car, _ = verify_roster_html(carousel_html, "https://cs.hust.edu.cn/szdw.htm", root_domain="hust.edu.cn")
    assert ok_car is False

    # Valid roster HTML on a root/index URL or DEPT_HOME/HOME/SCHOOLS_DIR must be rejected
    valid_html = """
    <html><body><main>
      <a href="https://cs.hust.edu.cn/info/1/zw.htm">张伟</a>
      <a href="https://cs.hust.edu.cn/info/2/lm.htm">李明</a>
      <a href="https://cs.hust.edu.cn/info/3/wf.htm">王芳</a>
    </main></body></html>
    """
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/", root_domain="hust.edu.cn")[0] is False
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/index.htm", root_domain="hust.edu.cn")[0] is False
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/main.psp", root_domain="hust.edu.cn")[0] is False
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/szdw.htm", root_domain="hust.edu.cn", node_type="DEPT_HOME")[0] is False
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/szdw.htm", root_domain="hust.edu.cn", node_type="SCHOOLS_DIR")[0] is False
    # Passes on actual faculty roster page
    assert verify_roster_html(valid_html, "https://cs.hust.edu.cn/szdw.htm", root_domain="hust.edu.cn", node_type="FACULTY_SECTION")[0] is True


@pytest.mark.asyncio
async def test_api_call_traces_comma_backup_503_failover_and_analytics_api():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_analytics")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        called_models: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content.decode())
            model = body.get("model", "")
            called_models.append(model)
            if "colab.test" in str(req.url):
                return httpx.Response(502, text="no tunnel")
            if model == "gemini-3-flash-preview":
                return httpx.Response(503, text="Service Unavailable")
            if model == "gemini-2.5-flash":
                return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})
            return httpx.Response(404)

        router = LLMRouter(
            colab=LLMEndpoint("colab_qwen", "https://colab.test/v1", "ck", "Qwen/Qwen2.5-7B-Instruct", tier=1, auth_header="X-API-Key"),
            primary=LLMEndpoint("primary", "", "", "", tier=2),
            backup=LLMEndpoint("backup", "https://gemini.test/v1", "bk", "gemini-3-flash-preview,gemini-2.5-flash", tier=3),
            trace_repo=repo,
        )
        res = await router.complete(
            [{"role": "user", "content": "ping"}],
            transport=httpx.MockTransport(handler),
            stage="unit_test",
        )
        assert res.ok is True
        assert res.data["model"] == "gemini-2.5-flash"
        assert called_models == ["Qwen/Qwen2.5-7B-Instruct", "gemini-3-flash-preview", "gemini-2.5-flash"]

        app = create_app(manager=mgr)
        app.state.repo = repo
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            r_ov = await client.get("/api/v1/analytics/overview")
            assert r_ov.status_code == 200
            ov = r_ov.json()
            assert ov["providers"]["colab_qwen"]["failed_count"] == 1
            assert ov["providers"]["colab_qwen"]["last_error"]["status"] == "tunnel_down_502"
            assert ov["providers"]["gemini"]["ok_count"] == 1
            assert ov["providers"]["gemini"]["failed_count"] == 1
            assert len(ov["failure_breakdown"]) >= 2

            r_tr = await client.get("/api/v1/analytics/traces?limit=10")
            assert r_tr.status_code == 200
            traces = r_tr.json()
            assert len(traces) == 3

            tid = traces[0]["trace_id"]
            r_det = await client.get(f"/api/v1/analytics/traces/{tid}")
            assert r_det.status_code == 200
            assert "request_payload" in r_det.json()
            assert "response_payload" in r_det.json()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_analytics")
        await mgr.close()


@pytest.mark.asyncio
async def test_bilingual_extraction_trees_extract_endpoint_and_exports():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_step2")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        await seed_universities(db)

        # Save a verified site tree for tsinghua.edu.cn
        await repo.upsert_site_tree(
            UniversitySiteTreeDoc(
                domain="tsinghua.edu.cn",
                root_url="https://www.tsinghua.edu.cn",
                nav_type="SEMANTIC_NAV",
                departments_map={"计算机系": "https://cs.tsinghua.edu.cn/"},
                verified_rosters={
                    "Computer Science::masters": VerifiedRosterEntry(
                        roster_url="https://cs.tsinghua.edu.cn/szdw.htm",
                        department_url="https://cs.tsinghua.edu.cn/",
                        strategy="TREE_DFS",
                        candidate_profile_count=1,
                    )
                },
            )
        )

        # Stub LLM returning bilingual fields + relative photo_url
        class StubRouter:
            async def complete(self, messages, **kwargs):
                return StepResult.success({
                    "content": json.dumps({
                        "name": "张伟",
                        "name_en": "Wei Zhang",
                        "title": "教授、博士生导师",
                        "title_en": "Professor, PhD Supervisor",
                        "email": "zw@tsinghua.edu.cn",
                        "degree_eligibility": ["masters", "phd"],
                        "research_interests": ["机器学习", "计算机视觉"],
                        "research_areas_en": ["Machine Learning", "Computer Vision"],
                        "photo_url": "/images/zhangwei.jpg",
                        "name_evidence_quote": "张伟",
                        "supervisor_evidence_quote": "博士生导师",
                    }, ensure_ascii=False),
                    "tier": 1,
                    "provider": "colab_qwen",
                    "model": "Qwen/Qwen2.5-7B-Instruct",
                    "latency_ms": 120,
                })

        snap = PageSnapshotDoc(
            url="https://cs.tsinghua.edu.cn/info/1001/zw.htm",
            domain="tsinghua.edu.cn",
            markdown="# 张伟\n教授，博士生导师\n![avatar](/images/zhangwei.jpg)\nEmail: zw@tsinghua.edu.cn\n研究方向：机器学习",
            sha256="abc123",
            breadcrumb="师资队伍",
        )

        class StubScraper:
            async def crawl_roster_urls(self, roster_url):
                return StepResult.success({"profile_urls": [snap.url], "used_playwright": False})

            async def fetch_and_snapshot_profile(self, url, dom):
                return StepResult.success(snap)

        extractor = Phase2ExtractorService(repo, router=StubRouter(), admin=AdminConfig())

        app = create_app(manager=mgr)
        app.state.repo = repo
        app.state.admin_config = AdminConfig(max_concurrent_universities=5)
        app.state.scraper = StubScraper()
        app.state.extractor = extractor

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Step 2: POST /api/v1/trees/extract
            r_ext = await client.post(
                "/api/v1/trees/extract",
                json={"country": "China", "regions": ["Beijing"], "department": "Computer Science", "degree": "masters", "tier": "top_5", "run_sync": True},
            )
            assert r_ext.status_code == 200
            edata = r_ext.json()
            assert edata["status"] == "COMPLETED"
            assert edata["scorecard"]["total_verified_professors"] == 1
            log_p = get_job_log_path(edata["job_id"])
            if log_p.exists():
                log_p.unlink()

            # Verify bilingual fields + absolute photo_url persisted
            profs = await repo.list_professors(domains=["tsinghua.edu.cn"])
            assert len(profs) == 1
            p = profs[0]
            assert p.name_en == "Wei Zhang"
            assert p.title_en == "Professor, PhD Supervisor"
            assert p.research_areas_en == ["Machine Learning", "Computer Vision"]
            assert p.photo_url == "https://cs.tsinghua.edu.cn/images/zhangwei.jpg"

            # Verify Export endpoints (Universities + Per-University Professors)
            r_u_csv = await client.get("/api/v1/export/universities?format=csv")
            assert r_u_csv.status_code == 200
            assert "tsinghua.edu.cn" in r_u_csv.text
            assert "SEMANTIC_NAV" in r_u_csv.text

            r_p_json = await client.get("/api/v1/export/professors?domain=tsinghua.edu.cn&format=json")
            assert r_p_json.status_code == 200
            pdata = r_p_json.json()
            assert len(pdata) == 1
            assert pdata[0]["name_en"] == "Wei Zhang"
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_step2")
        await mgr.close()
