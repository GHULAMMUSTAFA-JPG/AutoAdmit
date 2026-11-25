"""Resumable async orchestrator with Semaphore(8), per-university details, checkpointing, and full per-run JSONL logging."""

import asyncio
from collections import Counter
import uuid
from typing import Any

from app.core.llm_router import llm_router
from app.core.logging import current_domain, current_job_id, get_logger
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, UniversityDeptDoc, utc_now
from app.schemas.filters import AdminConfig
from app.services.phase1_discovery import Phase1DiscoveryService
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService

logger = get_logger("services.runner")


class PipelineRunner:
    """Runs Phase 1 + Phase 2 through a controlled async queue (default max_concurrent_universities=2)."""

    def __init__(
        self,
        repo: Repository,
        phase1: Phase1DiscoveryService,
        scraper: Phase2ScraperService,
        extractor: Phase2ExtractorService,
        admin: AdminConfig | None = None,
        max_university_concurrency: int | None = None,
    ) -> None:
        self.repo = repo
        self.phase1 = phase1
        self.scraper = scraper
        self.extractor = extractor
        self.admin = admin or AdminConfig()
        self._explicit_concurrency = max_university_concurrency

    def _get_concurrency(self) -> int:
        if self._explicit_concurrency is not None:
            return max(1, self._explicit_concurrency)
        return max(1, self.admin.max_concurrent_universities)

    async def run_job(
        self,
        *,
        domains: list[str],
        department: str,
        degree: str,
        job_id: str | None = None,
        request_meta: dict[str, Any] | None = None,
    ) -> JobDoc:
        """Creates or resumes a job, records per-university row details, and logs every step to logs/jobs/{job_id}.jsonl."""
        jid = job_id or f"job_{uuid.uuid4().hex[:8]}"
        job_token = current_job_id.set(jid)
        try:
            existing = await self.repo.get_job(jid)
            seed_docs = await self.repo.query_university_seeds(limit=2000)
            seed_map = {s.domain: s for s in seed_docs}

            if existing:
                job = existing
                job.status = "RUNNING"
            else:
                job = JobDoc(
                    job_id=jid,
                    request=request_meta or {"domains": domains, "department": department, "degree": degree},
                    status="RUNNING",
                    target_domains=list(domains),
                    completed_domains=[],
                    university_details={},
                    errors=[],
                    scorecard={
                        "winning_strategies": {},
                        "grounding_attempts": 0,
                        "grounding_passed": 0,
                        "grounding_pass_pct": 100.0,
                        "total_verified_professors": 0,
                        "failures": 0,
                    },
                )

            # Initialize queued row details for all target domains
            for dom in job.target_domains:
                if dom not in job.university_details:
                    sd = seed_map.get(dom)
                    job.university_details[dom] = {
                        "domain": dom,
                        "name": sd.name if sd else dom,
                        "chinese_name": sd.chinese_name if sd else "",
                        "region": sd.region if sd else "",
                        "rank": sd.rank if sd else None,
                        "winning_strategy": "PENDING",
                        "faculty_roster_url": None,
                        "department_url": None,
                        "professors_found": 0,
                        "professors_verified": 0,
                        "status": "QUEUED",
                        "error_code": None,
                        "detail": "",
                    }

            await self.repo.upsert_job(job)
            logger.info("job_started", job_id=jid, target_count=len(job.target_domains), department=department, degree=degree)

            checkpoint_lock = asyncio.Lock()
            strategies: Counter[str] = Counter(job.scorecard.get("winning_strategies", {}))
            work_queue: asyncio.Queue[str] = asyncio.Queue()
            for d in job.target_domains:
                if d not in job.completed_domains:
                    work_queue.put_nowait(d)
                else:
                    logger.info("runner_skip_completed", job_id=jid, domain=d)

            active_workers = 0
            slot_cond = asyncio.Condition()

            async def _worker() -> None:
                nonlocal active_workers
                while not work_queue.empty():
                    async with slot_cond:
                        while active_workers >= min(self._get_concurrency(), max(1, llm_router.active_concurrency)):
                            await slot_cond.wait_for(lambda: active_workers < min(self._get_concurrency(), max(1, llm_router.active_concurrency)))
                        try:
                            dom = work_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        active_workers += 1
                    dom_token = current_domain.set(dom)
                    try:
                        logger.info("university_started", job_id=jid, domain=dom, department=department, degree=degree)
                        job.university_details[dom]["status"] = "RUNNING"
                        job.queue_mode = llm_router.queue_mode
                        job.active_concurrency = min(self._get_concurrency(), max(1, llm_router.active_concurrency))

                        p1_res = await self.phase1.discover(dom, department, degree)
                        uni_found = 0
                        uni_verified = 0
                        uni_attempts = 0
                        uni_err: dict[str, Any] | None = None
                        win_strat = "NONE"
                        roster_url: str | None = None
                        dept_url: str | None = None
                        row_status = "NEEDS_REVIEW"

                        if not p1_res.ok:
                            uni_err = {"domain": dom, "stage": "phase1", "error_code": p1_res.error_code, "detail": p1_res.detail}
                            logger.warning("phase1_failed", job_id=jid, domain=dom, error_code=p1_res.error_code, detail=p1_res.detail)
                        else:
                            dept_doc = p1_res.data
                            win_strat = dept_doc.winning_strategy
                            roster_url = dept_doc.faculty_roster_url
                            dept_url = dept_doc.department_url
                            logger.info("phase1_succeeded", job_id=jid, domain=dom, winning_strategy=win_strat, roster_url=roster_url)

                            if roster_url:
                                crawl_res = await self.scraper.crawl_roster_urls(roster_url)
                                if not crawl_res.ok:
                                    uni_err = {"domain": dom, "stage": "phase2_crawl", "error_code": crawl_res.error_code, "detail": crawl_res.detail}
                                    logger.warning("phase2_crawl_failed", job_id=jid, domain=dom, error_code=crawl_res.error_code, detail=crawl_res.detail)
                                else:
                                    prof_urls = crawl_res.data["profile_urls"]
                                    roster_title = crawl_res.data.get("roster_title", "")
                                    uni_found = len(prof_urls)
                                    logger.info("phase2_crawl_done", job_id=jid, domain=dom, profiles_found=uni_found, used_playwright=crawl_res.data.get("used_playwright", False))

                                    for prof_url in prof_urls:
                                        snap_res = await self.scraper.fetch_and_snapshot_profile(prof_url, dom)
                                        if not snap_res.ok:
                                            logger.warning("phase2_snapshot_failed", job_id=jid, domain=dom, url=prof_url, error_code=snap_res.error_code)
                                            continue
                                        uni_attempts += 1
                                        ext_res = await self.extractor.extract_from_snapshot(
                                            snap_res.data, department=department, source_roster_url=roster_url, roster_title=roster_title
                                        )
                                        if ext_res.ok:
                                            uni_verified += 1
                                        else:
                                            logger.warning("phase2_extract_rejected", job_id=jid, domain=dom, url=prof_url, error_code=ext_res.error_code, detail=ext_res.detail)

                            # NEVER mark 0 verified professors as COMPLETE -> downgrade to NEEDS_REVIEW
                            if uni_verified > 0:
                                row_status = "COMPLETE"
                            else:
                                row_status = "NEEDS_REVIEW"
                                if not uni_err:
                                    uni_err = {
                                        "domain": dom,
                                        "stage": "phase2_verify",
                                        "error_code": "ZERO_VERIFIED_PROFESSORS",
                                        "detail": f"Phase 2 found {uni_found} links but verified 0 professors; marked NEEDS_REVIEW.",
                                    }
                                await self.repo.upsert_department_doc(
                                    UniversityDeptDoc(
                                        domain=dom,
                                        department=department,
                                        degree=degree,  # type: ignore[arg-type]
                                        department_url=dept_url,
                                        faculty_roster_url=roster_url,
                                        winning_strategy=win_strat,
                                        status="NEEDS_REVIEW",
                                        error_code="ZERO_VERIFIED_PROFESSORS",
                                    )
                                )
                                logger.warning("zero_verified_downgraded", job_id=jid, domain=dom, found=uni_found)

                        async with checkpoint_lock:
                            strategies[win_strat] += 1
                            job.scorecard["winning_strategies"] = dict(strategies)
                            job.scorecard["grounding_attempts"] = job.scorecard.get("grounding_attempts", 0) + uni_attempts
                            job.scorecard["grounding_passed"] = job.scorecard.get("grounding_passed", 0) + uni_verified
                            attempts = job.scorecard["grounding_attempts"]
                            passed = job.scorecard["grounding_passed"]
                            job.scorecard["grounding_pass_pct"] = round((passed / attempts) * 100.0, 2) if attempts else 100.0
                            job.scorecard["total_verified_professors"] = job.scorecard.get("total_verified_professors", 0) + uni_verified

                            job.university_details[dom].update({
                                "winning_strategy": win_strat,
                                "faculty_roster_url": roster_url,
                                "department_url": dept_url,
                                "professors_found": uni_found,
                                "professors_verified": uni_verified,
                                "status": row_status,
                                "error_code": uni_err["error_code"] if uni_err else None,
                                "detail": uni_err["detail"] if uni_err else "",
                            })

                            if uni_err:
                                job.errors.append(uni_err)
                                job.scorecard["failures"] = job.scorecard.get("failures", 0) + 1
                            job.queue_mode = llm_router.queue_mode
                            job.active_concurrency = min(self._get_concurrency(), max(1, llm_router.active_concurrency))
                            if dom not in job.completed_domains:
                                job.completed_domains.append(dom)
                            await self.repo.upsert_job(job)
                            logger.info("university_checkpointed", job_id=jid, domain=dom, status=row_status, professors_verified=uni_verified)
                    finally:
                        current_domain.reset(dom_token)
                        work_queue.task_done()
                        async with slot_cond:
                            active_workers = max(0, active_workers - 1)
                            slot_cond.notify_all()

            worker_count = min(self._get_concurrency(), max(1, work_queue.qsize()))
            await asyncio.gather(*[_worker() for _ in range(worker_count)])

            job.status = "COMPLETED"
            job.completed_at = utc_now()
            await self.repo.upsert_job(job)
            logger.info("runner_completed", job_id=jid, scorecard=job.scorecard)
            return job
        finally:
            current_job_id.reset(job_token)
