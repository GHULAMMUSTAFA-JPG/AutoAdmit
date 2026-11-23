"""Slice 6 Tests: 3-Step Smart Diff-Sync (304, Roster Diff, SHA-256), Resumable Runner Crash Recovery, & FastAPI Routes."""

import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.types import StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import JobDoc, PageSnapshotDoc, ProfessorDoc, UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.diff_sync import DiffSyncService
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService, clean_html_to_markdown, compute_sha256
from app.services.runner import PipelineRunner
from scripts.seed_universities import seed_universities


@pytest.mark.asyncio
async def test_diff_sync_304_and_sha256_zero_llm_calls():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s6_diff")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        html = "<html><body><h1>张伟</h1><p>博士生导师</p></body></html>"
        md, bc = clean_html_to_markdown(html)
        sha = compute_sha256(md)

        await repo.upsert_page_snapshot(
            PageSnapshotDoc(url="https://cs.u.edu.cn/p1", domain="u.edu.cn", markdown=md, sha256=sha, breadcrumb=bc, etag='"e1"')
        )
        await repo.upsert_page_snapshot(
            PageSnapshotDoc(url="https://cs.u.edu.cn/p2", domain="u.edu.cn", markdown=md, sha256=sha, breadcrumb=bc)
        )

        def handler(req: httpx.Request) -> httpx.Response:
            if str(req.url) == "https://cs.u.edu.cn/p1" and req.headers.get("if-none-match") == '"e1"':
                return httpx.Response(304)
            if str(req.url) == "https://cs.u.edu.cn/p2":
                return httpx.Response(200, text=html)
            return httpx.Response(404)

        router_mock = AsyncMock()
        transport = httpx.MockTransport(handler)
        scraper = Phase2ScraperService(repo, transport=transport, per_domain_delay=0.0)
        extractor = Phase2ExtractorService(repo, router=router_mock)
        diff_sync = DiffSyncService(repo, scraper, extractor, transport=transport)

        r304 = await diff_sync.sync_profile("https://cs.u.edu.cn/p1", "u.edu.cn", "Computer Science", "https://cs.u.edu.cn/roster")
        assert r304.ok is True
        assert r304.data["action"] == "skipped_304"
        assert r304.data["llm_called"] is False

        rsha = await diff_sync.sync_profile("https://cs.u.edu.cn/p2", "u.edu.cn", "Computer Science", "https://cs.u.edu.cn/roster")
        assert rsha.ok is True
        assert rsha.data["action"] == "skipped_sha256"
        assert rsha.data["llm_called"] is False

        router_mock.complete.assert_not_called()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s6_diff")
        await mgr.close()


@pytest.mark.asyncio
async def test_roster_diff_extracts_new_and_marks_vanished_possibly_inactive():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s6_roster")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        roster_url = "https://cs.u.edu.cn/roster"
        # Existing stored professor who vanished from live roster
        await repo.upsert_professor(
            ProfessorDoc(
                canonical_profile_url="https://cs.u.edu.cn/old.html",
                university_domain="u.edu.cn",
                department="Computer Science",
                source_roster_url=roster_url,
                name="王老",
                degree_eligibility=["phd"],
                status="ACTIVE",
            )
        )

        def handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u == roster_url:
                return httpx.Response(200, text='<html><body><a href="/new.html">李新</a></body></html>')
            if u == "https://cs.u.edu.cn/new.html":
                return httpx.Response(200, text="<html><body><h1>李新</h1><p>博士生导师</p></body></html>")
            return httpx.Response(404)

        router_mock = AsyncMock()
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "李新",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["phd"],
                "research_interests": ["AI"],
                "name_evidence_quote": "李新",
                "supervisor_evidence_quote": "博士生导师",
            }),
            "provider": "primary",
            "model": "mock",
        })
        transport = httpx.MockTransport(handler)
        scraper = Phase2ScraperService(repo, transport=transport, per_domain_delay=0.0)
        extractor = Phase2ExtractorService(repo, router=router_mock)
        diff_sync = DiffSyncService(repo, scraper, extractor, transport=transport)

        res = await diff_sync.sync_roster("u.edu.cn", "Computer Science", roster_url)
        assert res.ok is True
        assert res.data["new_extracted"] == 1
        assert res.data["marked_inactive"] == 1

        profs = {p.canonical_profile_url: p for p in await repo.list_professors_by_roster(roster_url)}
        assert profs["https://cs.u.edu.cn/old.html"].status == "POSSIBLY_INACTIVE"
        assert profs["https://cs.u.edu.cn/new.html"].status == "ACTIVE"
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s6_roster")
        await mgr.close()


@pytest.mark.asyncio
async def test_resumable_runner_skips_completed_domain_after_crash():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s6_resume")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        # Simulate crash after uni1 was already checkpointed
        await repo.upsert_job(
            JobDoc(
                job_id="job_resume_1",
                status="RUNNING",
                target_domains=["u1.edu.cn", "u2.edu.cn", "u3.edu.cn"],
                completed_domains=["u1.edu.cn"],
                scorecard={"winning_strategies": {"SEARCH_FIRST": 1}, "total_verified_professors": 2, "failures": 0},
            )
        )

        discovered_calls = []

        class StubPhase1:
            async def discover(self, dom, dept, deg):
                discovered_calls.append(dom)
                return StepResult.success(
                    UniversityDeptDoc(
                        domain=dom, department=dept, degree=deg,
                        faculty_roster_url=f"https://{dom}/roster",
                        winning_strategy="DIRECT_CRAWL", status="COMPLETE",
                    )
                )

        class StubScraper:
            async def crawl_roster_urls(self, url):
                return StepResult.success({"profile_urls": [], "used_playwright": False})

        runner = PipelineRunner(repo, StubPhase1(), StubScraper(), AsyncMock())
        finished = await runner.run_job(
            domains=["u1.edu.cn", "u2.edu.cn", "u3.edu.cn"],
            department="Computer Science",
            degree="masters",
            job_id="job_resume_1",
        )
        assert finished.status == "COMPLETED"
        assert "u1.edu.cn" not in discovered_calls
        assert set(discovered_calls) == {"u2.edu.cn", "u3.edu.cn"}
        assert set(finished.completed_domains) == {"u1.edu.cn", "u2.edu.cn", "u3.edu.cn"}
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s6_resume")
        await mgr.close()


@pytest.mark.asyncio
async def test_api_jobs_start_instant_db_return_and_admin_config():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s6_api")
    db = await mgr.connect()
    try:
        app = create_app(manager=mgr, admin_config=AdminConfig(max_departments_per_request=1))
        repo = Repository(db)
        app.state.repo = repo
        app.state.admin_config = AdminConfig(max_departments_per_request=1)

        await seed_universities(db)
        await repo.upsert_department_doc(
            UniversityDeptDoc(
                domain="tsinghua.edu.cn", department="Computer Science", degree="masters",
                faculty_roster_url="https://cs.tsinghua.edu.cn/szdw", winning_strategy="SEARCH_FIRST", status="COMPLETE"
            )
        )
        await repo.upsert_professor(
            ProfessorDoc(
                canonical_profile_url="https://cs.tsinghua.edu.cn/zw",
                university_domain="tsinghua.edu.cn",
                department="Computer Science",
                source_roster_url="https://cs.tsinghua.edu.cn/szdw",
                name="张伟",
                degree_eligibility=["masters"],
            )
        )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # POST /api/v1/jobs/start returns instant DB data ($0, no background job)
            r = await client.post(
                "/api/v1/jobs/start",
                json={"country": "China", "regions": ["Beijing"], "departments": ["Computer Science"], "degree": "masters", "tier": "top_1"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["source"] == "database"
            assert body["count"] == 1

            # GET /api/v1/system/summary
            rs = await client.get("/api/v1/system/summary")
            assert rs.status_code == 200
            assert rs.json()["professors"] == 1

            # GET & PATCH /api/v1/admin/config propagates to active services
            rc = await client.patch("/api/v1/admin/config", json={"enable_serper": False, "max_departments_per_request": 2})
            assert rc.status_code == 200
            assert rc.json()["enable_serper"] is False
            assert rc.json()["max_departments_per_request"] == 2

            # Unknown job_id returns 404
            r404 = await client.get("/api/v1/jobs/job_does_not_exist")
            assert r404.status_code == 404
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s6_api")
        await mgr.close()


@pytest.mark.asyncio
async def test_diff_sync_changed_sha256_triggers_re_extraction():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s6_sha_chg")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        old_html = "<html><body><h1>张伟</h1><p>硕士生导师</p></body></html>"
        new_html = "<html><body><h1>张伟</h1><p>博士生导师，新增多模态研究方向</p></body></html>"
        old_md, old_bc = clean_html_to_markdown(old_html)
        await repo.upsert_page_snapshot(
            PageSnapshotDoc(url="https://cs.u.edu.cn/p_chg", domain="u.edu.cn", markdown=old_md, sha256=compute_sha256(old_md), breadcrumb=old_bc)
        )

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=new_html)

        router_mock = AsyncMock()
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "张伟",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["phd"],
                "research_interests": ["多模态"],
                "name_evidence_quote": "张伟",
                "supervisor_evidence_quote": "博士生导师",
            }),
            "provider": "primary",
            "model": "mock",
        })
        transport = httpx.MockTransport(handler)
        scraper = Phase2ScraperService(repo, transport=transport, per_domain_delay=0.0)
        extractor = Phase2ExtractorService(repo, router=router_mock)
        diff_sync = DiffSyncService(repo, scraper, extractor, transport=transport)

        res = await diff_sync.sync_profile("https://cs.u.edu.cn/p_chg", "u.edu.cn", "Computer Science", "https://cs.u.edu.cn/roster")
        assert res.ok is True
        assert res.data["action"] == "re_extracted"
        assert res.data["llm_called"] is True
        router_mock.complete.assert_called_once()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s6_sha_chg")
        await mgr.close()
