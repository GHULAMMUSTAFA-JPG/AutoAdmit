"""Slice 3 Tests: Phase 1 Multi-Strategy Discovery (DB Hit, A Serper, B Direct+Colab/CPU, robots.txt, D Nav Agent)."""

from unittest.mock import AsyncMock
import httpx
import pytest

from app.core.config import settings
from app.core.types import ErrorCode, StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.schemas.entities import UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.colab_client import ColabClient
from app.services.phase1_discovery import Phase1DiscoveryService


@pytest.mark.asyncio
async def test_phase1_existing_db_record_returns_with_zero_network_calls():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_db")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        await repo.upsert_department_doc(
            UniversityDeptDoc(
                domain="tsinghua.edu.cn",
                department="Computer Science",
                degree="masters",
                faculty_roster_url="https://cs.tsinghua.edu.cn/szdw",
                winning_strategy="SEARCH_FIRST",
                status="COMPLETE",
            )
        )

        called = []
        def fail_if_called(req: httpx.Request) -> httpx.Response:
            called.append(str(req.url))
            return httpx.Response(500)

        svc = Phase1DiscoveryService(repo, transport=httpx.MockTransport(fail_if_called))
        res = await svc.discover("tsinghua.edu.cn", "Computer Science", "masters")
        assert res.ok is True
        assert res.data.faculty_roster_url == "https://cs.tsinghua.edu.cn/szdw"
        assert len(called) == 0
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_db")
        await mgr.close()


@pytest.mark.asyncio
async def test_phase1_strategy_a_serper_hit_skips_bcd(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "fake-serper-key")
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_a")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def handler(req: httpx.Request) -> httpx.Response:
            if "serper.dev" in str(req.url):
                return httpx.Response(200, json={"organic": [{"title": "CS Faculty", "link": "https://cs.pku.edu.cn/szdw", "snippet": "PhD supervisors"}]})
            if str(req.url) == "https://cs.pku.edu.cn/szdw":
                return httpx.Response(
                    200,
                    text="""<html><body><h1>计算机学院师资队伍 博士生导师</h1><main>
                      <a href="https://cs.pku.edu.cn/info/1/zw.htm">张伟</a>
                      <a href="https://cs.pku.edu.cn/info/2/lm.htm">李明</a>
                      <a href="https://cs.pku.edu.cn/info/3/wf.htm">王芳</a>
                    </main></body></html>""",
                )
            return httpx.Response(404)

        nav_mock = AsyncMock()
        svc = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_colab_bridge=False, enable_playwright=False),
            nav_agent=nav_mock,
            transport=httpx.MockTransport(handler),
        )
        res = await svc.discover("pku.edu.cn", "Computer Science", "phd")
        assert res.ok is True
        assert res.data.winning_strategy == "SERPER_LLM_FALLBACK"
        assert res.data.faculty_roster_url == "https://cs.pku.edu.cn/szdw"
        nav_mock.navigate.assert_not_called()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_a")
        await mgr.close()


@pytest.mark.asyncio
async def test_phase1_strategy_b_colab_online_and_cpu_fallback(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_b")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u.endswith("/robots.txt"):
                return httpx.Response(200, text="User-agent: *\nAllow: /")
            if u == "https://www.zju.edu.cn":
                return httpx.Response(200, text='<html><body><a href="https://cs.zju.edu.cn/faculty">计算机学院师资队伍</a></body></html>')
            if u == "https://cs.zju.edu.cn/faculty":
                return httpx.Response(
                    200,
                    text="""<html><body><h1>计算机学院 硕士生导师名录</h1><main>
                      <a href="https://cs.zju.edu.cn/info/1/zw.htm">张伟</a>
                      <a href="https://cs.zju.edu.cn/info/2/lm.htm">李明</a>
                      <a href="https://cs.zju.edu.cn/info/3/wf.htm">王芳</a>
                    </main></body></html>""",
                )
            if u == "https://colab.test/score-links":
                return httpx.Response(200, json={"results": [{"text": "计算机学院师资队伍", "href": "https://cs.zju.edu.cn/faculty", "score": 0.95}]})
            return httpx.Response(404)

        # 1. Tree-First DFS discovery (masters)
        svc1 = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_colab_bridge=False, enable_playwright=False),
            transport=httpx.MockTransport(handler),
        )
        res1 = await svc1.discover("zju.edu.cn", "Computer Science", "masters")
        assert res1.ok is True
        assert res1.data.winning_strategy == "TREE_DFS"
        assert res1.data.faculty_roster_url == "https://cs.zju.edu.cn/faculty"

        # 2. Tree-First DFS discovery (phd) with Colab offline
        svc2 = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_colab_bridge=False, enable_playwright=False),
            transport=httpx.MockTransport(handler),
        )
        res2 = await svc2.discover("zju.edu.cn", "Computer Science", "phd")
        assert res2.ok is True
        assert res2.data.winning_strategy == "TREE_DFS"
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_b")
        await mgr.close()


@pytest.mark.asyncio
async def test_phase1_robots_disallow_routes_to_needs_review(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_robots")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def handler(req: httpx.Request) -> httpx.Response:
            if str(req.url).endswith("/robots.txt"):
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(200, text="should not be fetched")

        svc = Phase1DiscoveryService(repo, transport=httpx.MockTransport(handler))
        res = await svc.discover("blocked.edu.cn", "Computer Science", "masters")
        assert res.ok is False
        assert res.error_code == ErrorCode.ROBOTS_DISALLOWED.value
        assert await db["needs_review"].count_documents({"domain": "blocked.edu.cn"}) == 1
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_robots")
        await mgr.close()


@pytest.mark.asyncio
async def test_phase1_strategy_d_nav_agent_and_flag_respect(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_d")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def empty_handler(req: httpx.Request) -> httpx.Response:
            if str(req.url).endswith("/robots.txt"):
                return httpx.Response(404)
            return httpx.Response(200, text="<html><body>Empty shell</body></html>")

        nav_mock = AsyncMock()
        nav_mock.navigate.return_value = StepResult.success({
            "faculty_roster_url": "https://cs.hard.edu.cn/roster",
            "navigation_path": [{"url": "https://www.hard.edu.cn", "chosen_link": "https://cs.hard.edu.cn/roster", "reason": "direct"}],
        })

        # Flag OFF -> agent must NOT be called
        svc_off = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_agent_fallback=False, enable_playwright=False),
            nav_agent=nav_mock,
            transport=httpx.MockTransport(empty_handler),
        )
        res_off = await svc_off.discover("hard.edu.cn", "Computer Science", "masters")
        assert res_off.ok is False
        nav_mock.navigate.assert_not_called()

        # Flag ON -> agent rescues and saves COMPLETE
        svc_on = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_agent_fallback=True, enable_playwright=False),
            nav_agent=nav_mock,
            transport=httpx.MockTransport(empty_handler),
        )
        res_on = await svc_on.discover("hard.edu.cn", "Computer Science", "phd")
        assert res_on.ok is True
        assert res_on.data.winning_strategy == "NAV_AGENT"
        nav_mock.navigate.assert_called_once()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_d")
        await mgr.close()


@pytest.mark.asyncio
async def test_phase1_strategy_c_waf_412_playwright_and_verification_gate_rejects_login(monkeypatch):
    from app.services.phase1_discovery import is_valid_faculty_page

    # Verification gate rejects login & news pages even if HTTP 200
    assert is_valid_faculty_page(200, "<html><body>统一身份认证 CAS Login 师资</body></html>", "https://u.edu.cn/login") is False
    assert is_valid_faculty_page(200, "<html><body>新闻中心 师资新闻</body></html>", "https://u.edu.cn/news") is False
    assert is_valid_faculty_page(200, "<html><body>计算机学院 博士生导师 师资队伍</body></html>", "https://cs.u.edu.cn/szdw") is True

    # Strategy C: WAF 412 triggers Playwright render fallback and succeeds
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s3_waf")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def waf_handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u.endswith("/robots.txt"):
                return httpx.Response(404)
            if u == "https://www.waf.edu.cn":
                return httpx.Response(412, text="WAF Challenge")
            if u == "https://cs.waf.edu.cn/szdw":
                return httpx.Response(
                    200,
                    text="""<html><body><h1>计算机学院 硕士生导师</h1><main>
                      <a href="https://cs.waf.edu.cn/info/1/zw.htm">张伟</a>
                      <a href="https://cs.waf.edu.cn/info/2/lm.htm">李明</a>
                      <a href="https://cs.waf.edu.cn/info/3/wf.htm">王芳</a>
                    </main></body></html>""",
                )
            return httpx.Response(404)

        pw_mock = AsyncMock(
            return_value=(200, "https://www.waf.edu.cn", '<html><body><nav><a href="https://cs.waf.edu.cn/szdw">计算机学院师资队伍</a></nav></body></html>')
        )
        svc = Phase1DiscoveryService(
            repo,
            admin=AdminConfig(enable_playwright=True, enable_agent_fallback=False, enable_colab_bridge=False),
            transport=httpx.MockTransport(waf_handler),
            playwright_fetcher=pw_mock,
        )
        res = await svc.discover("waf.edu.cn", "Computer Science", "masters")
        assert res.ok is True
        assert res.data.winning_strategy == "TREE_DFS"
        pw_mock.assert_called_once()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s3_waf")
        await mgr.close()
