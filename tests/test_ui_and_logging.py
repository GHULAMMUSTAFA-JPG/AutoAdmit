"""Tests for ported app/static UI, GET /, /professors, /needs-review, per-university job details, and un-truncated per-run logs."""

import json
from unittest.mock import AsyncMock
import httpx
import pytest

from app.core.config import settings
from app.core.logging import get_job_log_path, get_logger, current_job_id, current_domain
from app.core.types import StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import NeedsReviewDoc, ProfessorDoc, UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.runner import PipelineRunner
from scripts.seed_universities import seed_universities


@pytest.mark.asyncio
async def test_ui_root_professors_needs_review_and_job_details():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_ui")
    db = await mgr.connect()
    try:
        app = create_app(manager=mgr, admin_config=AdminConfig())
        repo = Repository(db)
        app.state.repo = repo
        app.state.admin_config = AdminConfig()

        await seed_universities(db)
        await repo.upsert_professor(
            ProfessorDoc(
                canonical_profile_url="https://cs.tsinghua.edu.cn/zw",
                university_domain="tsinghua.edu.cn",
                department="Computer Science",
                source_roster_url="https://cs.tsinghua.edu.cn/szdw",
                name="张伟",
                email="zw@tsinghua.edu.cn",
                email_status="FOUND",
                degree_eligibility=["phd"],
                research_interests=["AI", "Vision"],
                supervisor_evidence_quote="博士生导师",
            )
        )
        await repo.add_needs_review(
            NeedsReviewDoc(
                domain="blocked.edu.cn",
                url="https://www.blocked.edu.cn",
                stage="phase1_discovery",
                error_code="ROBOTS_DISALLOWED",
                detail="Disallowed by robots.txt",
            )
        )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. GET / serves app/static/index.html
            r_root = await client.get("/")
            assert r_root.status_code == 200
            assert "AutoAdmit P12" in r_root.text
            assert "/api/v1/admin/config" in r_root.text

            # 2. GET /api/v1/professors
            r_profs = await client.get("/api/v1/professors?domain=tsinghua.edu.cn&email_status=FOUND")
            assert r_profs.status_code == 200
            profs = r_profs.json()
            assert len(profs) == 1
            assert profs[0]["name"] == "张伟"

            # 3. GET /api/v1/needs-review
            r_rev = await client.get("/api/v1/needs-review")
            assert r_rev.status_code == 200
            revs = r_rev.json()
            assert len(revs) == 1
            assert revs[0]["error_code"] == "ROBOTS_DISALLOWED"

            # 4. Per-university details in JobDoc via PipelineRunner
            class StubP1:
                async def discover(self, dom, dept, deg):
                    return StepResult.success(
                        UniversityDeptDoc(
                            domain=dom, department=dept, degree=deg,
                            faculty_roster_url=f"https://{dom}/szdw",
                            winning_strategy="SEARCH_FIRST", status="COMPLETE",
                        )
                    )

            class StubScraper:
                async def crawl_roster_urls(self, url):
                    return StepResult.success({"profile_urls": [], "used_playwright": False})

            runner = PipelineRunner(repo, StubP1(), StubScraper(), AsyncMock())
            job = await runner.run_job(domains=["tsinghua.edu.cn"], department="Computer Science", degree="masters", job_id="job_ui_detail_test")

            r_job = await client.get(f"/api/v1/jobs/{job.job_id}")
            assert r_job.status_code == 200
            jdata = r_job.json()
            assert "tsinghua.edu.cn" in jdata["university_details"]
            row = jdata["university_details"]["tsinghua.edu.cn"]
            assert row["winning_strategy"] == "SEARCH_FIRST"
            assert row["faculty_roster_url"] == "https://tsinghua.edu.cn/szdw"
            assert row["status"] == "NEEDS_REVIEW"  # 0 verified professors never marked COMPLETE

            # Clean up generated test log file
            log_path = get_job_log_path(job.job_id)
            if log_path.exists():
                log_path.unlink()
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_ui")
        await mgr.close()


@pytest.mark.asyncio
async def test_untruncated_per_run_logs_offset_pagination_and_download():
    job_id = "job_log_pagination_test"
    log_path = get_job_log_path(job_id)
    if log_path.exists():
        log_path.unlink()

    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_logs")
    app = create_app(manager=mgr)

    try:
        # Emit 1,250 structured log entries (>2 pages of 500) to verify ZERO truncation
        log = get_logger("test.untruncated")
        t_job = current_job_id.set(job_id)
        t_dom = current_domain.set("tsinghua.edu.cn")
        try:
            for i in range(1250):
                log.info("step_event", seq=i)
        finally:
            current_domain.reset(t_dom)
            current_job_id.reset(t_job)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            collected = []
            offset = 0
            while True:
                r = await client.get(f"/api/v1/jobs/{job_id}/logs?offset={offset}&limit=500")
                assert r.status_code == 200
                payload = r.json()
                assert payload["total"] == 1250
                collected.extend(payload["entries"])
                offset = payload["next_offset"]
                if offset >= payload["total"]:
                    break

            assert len(collected) == 1250
            assert collected[0]["seq"] == 0
            assert collected[-1]["seq"] == 1249

            # Download endpoint returns full raw JSONL file
            r_dl = await client.get(f"/api/v1/jobs/{job_id}/logs/download")
            assert r_dl.status_code == 200
            lines = [ln for ln in r_dl.text.splitlines() if ln.strip()]
            assert len(lines) == 1250
            assert json.loads(lines[-1])["seq"] == 1249
    finally:
        if log_path.exists():
            log_path.unlink()
