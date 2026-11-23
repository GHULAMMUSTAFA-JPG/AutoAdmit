"""Resumable async orchestrator with Semaphore(8) across universities, per-university checkpointing, and Run Scorecard."""

import asyncio
from collections import Counter
import uuid
from typing import Any

from app.core.logging import get_logger
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, utc_now
from app.services.phase1_discovery import Phase1DiscoveryService
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService

logger = get_logger("services.runner")


class PipelineRunner:
    """Runs Phase 1 + Phase 2 across multiple universities with checkpoint/resume and scorecard tracking."""

    def __init__(
        self,
        repo: Repository,
        phase1: Phase1DiscoveryService,
        scraper: Phase2ScraperService,
        extractor: Phase2ExtractorService,
        max_university_concurrency: int = 8,
    ) -> None:
        self.repo = repo
        self.phase1 = phase1
        self.scraper = scraper
        self.extractor = extractor
        self._uni_sem = asyncio.Semaphore(max(1, max_university_concurrency))

    async def run_job(
        self,
        *,
        domains: list[str],
        department: str,
        degree: str,
        job_id: str | None = None,
        request_meta: dict[str, Any] | None = None,
    ) -> JobDoc:
        """Creates or resumes a job, skipping already-checkpointed domains and updating scorecard after each uni."""
        jid = job_id or f"job_{uuid.uuid4().hex[:8]}"
        existing = await self.repo.get_job(jid)
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
        await self.repo.upsert_job(job)

        checkpoint_lock = asyncio.Lock()
        strategies: Counter[str] = Counter(job.scorecard.get("winning_strategies", {}))

        async def _run_one_university(dom: str) -> None:
            if dom in job.completed_domains:
                logger.info("runner_skip_completed", job_id=jid, domain=dom)
                return

            async with self._uni_sem:
                p1_res = await self.phase1.discover(dom, department, degree)
                uni_verified = 0
                uni_attempts = 0
                uni_err: dict[str, Any] | None = None
                win_strat = "NONE"

                if not p1_res.ok:
                    uni_err = {"domain": dom, "stage": "phase1", "error_code": p1_res.error_code, "detail": p1_res.detail}
                else:
                    dept_doc = p1_res.data
                    win_strat = dept_doc.winning_strategy
                    roster_url = dept_doc.faculty_roster_url
                    if roster_url:
                        crawl_res = await self.scraper.crawl_roster_urls(roster_url)
                        if not crawl_res.ok:
                            uni_err = {"domain": dom, "stage": "phase2_crawl", "error_code": crawl_res.error_code, "detail": crawl_res.detail}
                        else:
                            # Sequential within a single domain (politeness)
                            for prof_url in crawl_res.data["profile_urls"]:
                                snap_res = await self.scraper.fetch_and_snapshot_profile(prof_url, dom)
                                if not snap_res.ok:
                                    continue
                                uni_attempts += 1
                                ext_res = await self.extractor.extract_from_snapshot(
                                    snap_res.data, department=department, source_roster_url=roster_url
                                )
                                if ext_res.ok:
                                    uni_verified += 1

                async with checkpoint_lock:
                    strategies[win_strat] += 1
                    job.scorecard["winning_strategies"] = dict(strategies)
                    job.scorecard["grounding_attempts"] = job.scorecard.get("grounding_attempts", 0) + uni_attempts
                    job.scorecard["grounding_passed"] = job.scorecard.get("grounding_passed", 0) + uni_verified
                    attempts = job.scorecard["grounding_attempts"]
                    passed = job.scorecard["grounding_passed"]
                    job.scorecard["grounding_pass_pct"] = round((passed / attempts) * 100.0, 2) if attempts else 100.0
                    job.scorecard["total_verified_professors"] = job.scorecard.get("total_verified_professors", 0) + uni_verified
                    if uni_err:
                        job.errors.append(uni_err)
                        job.scorecard["failures"] = job.scorecard.get("failures", 0) + 1
                    if dom not in job.completed_domains:
                        job.completed_domains.append(dom)
                    await self.repo.upsert_job(job)

        await asyncio.gather(*[_run_one_university(d) for d in job.target_domains])

        job.status = "COMPLETED"
        job.completed_at = utc_now()
        await self.repo.upsert_job(job)
        logger.info("runner_completed", job_id=jid, scorecard=job.scorecard)
        return job
