"""Part 5 Regression Tests:
- Phase 2A link extractor chrome stripping, denylist, and external domain blocking
- Deterministic Roster Verification Gate (>= 3 profile links)
- 0 verified professors -> NEEDS_REVIEW (never COMPLETE)
- 3-Tier LLM Router failover (Colab offline -> Tier 2 429 backoff -> Tier 3 Gemini)
- SiteTreeBuilder: Pruned BFS -> Targeted DFS, departments_map, backtracking, markdown_tree persistence
- POST /api/v1/trees/build & GET /api/v1/trees/{domain}
"""

from unittest.mock import AsyncMock
import httpx
import pytest

from app.core.config import settings
from app.core.llm_router import COLAB_QWEN_MODEL, LLMEndpoint, LLMRouter
from app.core.types import StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.phase2_scraper import extract_profile_urls, verify_roster_html
from app.services.runner import PipelineRunner
from app.services.site_tree_builder import SiteTreeBuilder
from scripts.seed_universities import seed_universities


def test_phase2a_extractor_strips_chrome_blocks_external_and_denylist():
    html = """
    <html><body>
      <header>
        <nav>
          <a href="https://www.tsinghua.edu.cn/About_Us.htm">About Us</a>
          <a href="https://www.tsinghua.edu.cn/News/index.htm">张伟</a>
          <a href="https://www.tsinghua.edu.cn/intlLogin">Login</a>
          <a href="https://720yun.com/t/tour">李明</a>
        </nav>
      </header>
      <main>
        <a href="https://cs.tsinghua.edu.cn/info/1001/zhangwei.htm">张伟</a>
        <a href="https://cs.tsinghua.edu.cn/info/1002/liming.htm">李明</a>
        <a href="https://cs.tsinghua.edu.cn/info/1003/wangfang.htm">王芳</a>
        <a href="https://720yun.com/t/vr">陈华</a>
        <a href="https://ev.tsinghua.edu.cn/Schools___Colleges/cs.htm">赵雷</a>
        <a href="https://cs.tsinghua.edu.cn/index.htm">孙强</a>
      </main>
      <footer><a href="https://cs.tsinghua.edu.cn/info/999/footer.htm">周杰</a></footer>
    </body></html>
    """
    urls = extract_profile_urls(html, "https://cs.tsinghua.edu.cn/szdw.htm", root_domain="tsinghua.edu.cn")
    assert set(urls) == {
        "https://cs.tsinghua.edu.cn/info/1001/zhangwei.htm",
        "https://cs.tsinghua.edu.cn/info/1002/liming.htm",
        "https://cs.tsinghua.edu.cn/info/1003/wangfang.htm",
    }

    # Deterministic Roster Verification Gate (>= 3 profiles passes; < 3 fails)
    ok_3, _ = verify_roster_html(html, "https://cs.tsinghua.edu.cn/szdw.htm", root_domain="tsinghua.edu.cn", min_profiles=3)
    assert ok_3 is True

    small_html = """<html><body><main>
      <a href="https://cs.tsinghua.edu.cn/info/1001/zhangwei.htm">张伟</a>
      <a href="https://cs.tsinghua.edu.cn/info/1002/liming.htm">李明</a>
    </main></body></html>"""
    ok_2, _ = verify_roster_html(small_html, "https://cs.tsinghua.edu.cn/szdw.htm", root_domain="tsinghua.edu.cn", min_profiles=3)
    assert ok_2 is False


@pytest.mark.asyncio
async def test_runner_zero_verified_professors_saves_needs_review_not_complete():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_zero_ver")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        class StubP1:
            async def discover(self, dom, dept, deg):
                doc = UniversityDeptDoc(
                    domain=dom, department=dept, degree=deg,
                    faculty_roster_url=f"https://cs.{dom}/szdw", winning_strategy="TREE_DFS", status="COMPLETE"
                )
                await repo.upsert_department_doc(doc)
                return StepResult.success(doc)

        class StubScraper:
            async def crawl_roster_urls(self, url):
                return StepResult.success({"profile_urls": [], "used_playwright": False})

        runner = PipelineRunner(repo, StubP1(), StubScraper(), AsyncMock(), admin=AdminConfig(max_concurrent_universities=2))
        job = await runner.run_job(domains=["zero.edu.cn"], department="Computer Science", degree="masters", job_id="job_zero_test")

        assert job.university_details["zero.edu.cn"]["status"] == "NEEDS_REVIEW"
        stored_dept = await repo.get_department_doc("zero.edu.cn", "Computer Science", "masters")
        assert stored_dept is not None
        assert stored_dept.status == "NEEDS_REVIEW"
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_zero_ver")
        await mgr.close()


@pytest.mark.asyncio
async def test_three_tier_llm_router_colab_offline_deepseek_429_backoff_gemini_wins():
    call_log = []

    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        call_log.append(u)
        if "colab.test" in u:
            raise httpx.ConnectError("Colab offline")
        if "coarena.test" in u:
            return httpx.Response(429, text="Rate limited")
        if "gemini.test" in u:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"winner":"gemini"}'}}]})
        return httpx.Response(404)

    router = LLMRouter(
        colab=LLMEndpoint("colab_qwen", "https://colab.test/v1", "ck", COLAB_QWEN_MODEL, tier=1, auth_header="X-API-Key"),
        primary=LLMEndpoint("primary", "https://coarena.test/v1", "pk", "deepseek-v4-1-flash-1017", tier=2),
        backup=LLMEndpoint("backup", "https://gemini.test/v1", "bk", "gemini-3-flash-preview", tier=3),
        backoff_delays=(0.0, 0.0),  # 2 retries on Tier 2 before failing over to Tier 3
        colab_cooldown_sec=60.0,
    )
    res = await router.complete([{"role": "user", "content": "hi"}], transport=httpx.MockTransport(handler))
    assert res.ok is True
    assert res.data["tier"] == 3
    assert res.data["provider"] == "backup"
    # 1 colab attempt (trips circuit) + 3 primary attempts (1 initial + 2 backoff retries) + 1 backup attempt
    assert len(call_log) == 5

    # Second call skips Colab immediately due to 60s circuit-breaker
    call_log.clear()
    res2 = await router.complete([{"role": "user", "content": "hi2"}], transport=httpx.MockTransport(handler))
    assert res2.ok is True
    assert all("colab.test" not in u for u in call_log)


@pytest.mark.asyncio
async def test_site_tree_builder_bfs_dfs_departments_map_backtracking_and_api():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_trees")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        await seed_universities(db)

        def handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u.endswith("/robots.txt"):
                return httpx.Response(404)
            if u == "https://www.tsinghua.edu.cn":
                return httpx.Response(
                    200,
                    text="""<html><body>
                      <header><nav>
                        <a href="https://ev.tsinghua.edu.cn/deadend">English Brochure</a>
                        <a href="https://www.tsinghua.edu.cn/yxsz.htm">院系设置</a>
                      </nav></header>
                    </body></html>""",
                )
            if u == "https://ev.tsinghua.edu.cn/deadend":
                return httpx.Response(200, text="<html><body><p>Brochure with 0 profiles</p></body></html>")
            if u == "https://www.tsinghua.edu.cn/yxsz.htm":
                return httpx.Response(
                    200,
                    text="""<html><body><h1>院系设置</h1><main>
                      <a href="https://cs.tsinghua.edu.cn/">计算机科学与技术系</a>
                      <a href="https://ai.tsinghua.edu.cn/">人工智能学院</a>
                      <a href="https://ee.tsinghua.edu.cn/">电子工程系</a>
                      <a href="https://se.tsinghua.edu.cn/">软件学院</a>
                    </main></body></html>""",
                )
            if u == "https://cs.tsinghua.edu.cn/":
                return httpx.Response(
                    200,
                    text="""<html><body>
                      <nav><a href="https://cs.tsinghua.edu.cn/szdw.htm">师资队伍</a></nav>
                    </body></html>""",
                )
            if u == "https://cs.tsinghua.edu.cn/szdw.htm":
                return httpx.Response(
                    200,
                    text="""<html><body><main>
                      <a href="https://cs.tsinghua.edu.cn/info/1/zw.htm">张伟</a>
                      <a href="https://cs.tsinghua.edu.cn/info/2/lm.htm">李明</a>
                      <a href="https://cs.tsinghua.edu.cn/info/3/wf.htm">王芳</a>
                    </main></body></html>""",
                )
            return httpx.Response(404)

        # Force deterministic heuristic ranker by providing empty router
        empty_router = LLMRouter(
            colab=LLMEndpoint("c", "", "", "", tier=1),
            primary=LLMEndpoint("p", "", "", "", tier=2),
            backup=LLMEndpoint("b", "", "", "", tier=3),
        )
        builder = SiteTreeBuilder(
            repo,
            admin=AdminConfig(enable_serper=False, enable_playwright=False),
            router=empty_router,
            transport=httpx.MockTransport(handler),
        )
        res = await builder.build_and_find_roster("tsinghua.edu.cn", "Computer Science", "masters")
        assert res.ok is True
        assert res.data["strategy"] == "TREE_DFS"
        assert res.data["roster_url"] == "https://cs.tsinghua.edu.cn/szdw.htm"
        assert res.data["candidate_profile_count"] == 3

        saved_tree = await repo.get_site_tree("tsinghua.edu.cn")
        assert saved_tree is not None
        assert "计算机科学与技术系" in saved_tree.departments_map
        assert "人工智能学院" in saved_tree.departments_map
        assert "Computer Science::masters" in saved_tree.verified_rosters
        assert "szdw.htm" in saved_tree.markdown_tree

        # Verify POST /api/v1/trees/build & GET /api/v1/trees/{domain}
        app = create_app(manager=mgr)
        app.state.repo = repo
        app.state.admin_config = AdminConfig(max_concurrent_universities=2)
        app.state.tree_builder = builder

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            r_build = await client.post(
                "/api/v1/trees/build",
                json={"country": "China", "regions": ["Beijing"], "department": "Computer Science", "degree": "masters", "tier": "top_1", "run_sync": True},
            )
            assert r_build.status_code == 200
            bdata = r_build.json()
            assert bdata["scorecard"]["rosters_verified"] == 1

            r_list = await client.get("/api/v1/trees")
            assert r_list.status_code == 200
            assert any(t["domain"] == "tsinghua.edu.cn" for t in r_list.json())

            r_get = await client.get("/api/v1/trees/tsinghua.edu.cn")
            assert r_get.status_code == 200
            gdata = r_get.json()
            assert "markdown_tree" in gdata
            assert "Computer Science::masters" in gdata["verified_rosters"]
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_trees")
        await mgr.close()
