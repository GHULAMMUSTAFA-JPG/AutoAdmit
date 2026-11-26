"""Tree-Only Discovery & Verification endpoints (`POST /api/v1/trees/build`, `GET /api/v1/trees`, `GET /api/v1/trees/{domain}`)."""

import asyncio
from typing import Any, Literal
import uuid
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.llm_router import llm_router
from app.core.logging import current_domain, current_job_id, get_logger
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, UniversityDeptDoc, utc_now
from app.schemas.filters import AdminConfig, parse_tier_limit
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService
from app.services.runner import WORKER_TIMEOUT_SEC, is_canary_sentinel_mismatch
from app.services.site_tree_builder import SiteTreeBuilder
from scripts.seed_universities import filter_university_seeds

router = APIRouter(prefix="/api/v1/trees", tags=["Site Trees"])
logger = get_logger("api.routes_trees")


class BuildTreesRequest(BaseModel):
    country: str = Field(default="China")
    regions: list[str] = Field(default_factory=list)
    department: str = Field(default="Computer Science")
    degree: Literal["masters", "phd", "both"] = Field(default="masters")
    tier: str | None = Field(default="top_10")
    force_refresh: bool = Field(default=False)
    run_sync: bool = Field(default=False)


class ExtractFromTreesRequest(BaseModel):
    country: str = Field(default="China")
    regions: list[str] = Field(default_factory=list)
    department: str = Field(default="Computer Science")
    degree: Literal["masters", "phd", "both"] = Field(default="masters")
    tier: str | None = Field(default="top_10")
    force_reextract: bool = Field(default=False)
    run_sync: bool = Field(default=False)


async def _run_tree_build_job(
    repo: Repository,
    builder: SiteTreeBuilder,
    admin: AdminConfig,
    job: JobDoc,
    department: str,
    degree: str,
    force_refresh: bool,
) -> JobDoc:
    jid = job.job_id
    job_token = current_job_id.set(jid)
    try:
        job.status = "RUNNING"
        await repo.upsert_job(job)
        logger.info("tree_job_started", job_id=jid, target_count=len(job.target_domains), department=department, degree=degree)

        lock = asyncio.Lock()
        queue: asyncio.Queue[str] = asyncio.Queue()
        for d in job.target_domains:
            queue.put_nowait(d)

        total_hops = 0
        rosters_verified = 0
        departments_mapped = 0
        bfs_dfs_wins = 0
        serper_fallback_wins = 0
        cache_wins = 0
        failures = 0

        async def _worker() -> None:
            nonlocal total_hops, rosters_verified, departments_mapped, bfs_dfs_wins, serper_fallback_wins, cache_wins, failures
            while not queue.empty():
                try:
                    dom = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                dom_token = current_domain.set(dom)
                try:
                    job.university_details[dom]["status"] = "RUNNING"
                    try:
                        res = await asyncio.wait_for(
                            builder.build_and_find_roster(dom, department, degree, force_refresh=force_refresh),
                            timeout=WORKER_TIMEOUT_SEC,
                        )
                    except asyncio.TimeoutError:
                        from app.core.types import StepResult
                        res = StepResult.fail("WORKER_TIMEOUT", f"Tree builder exceeded {int(WORKER_TIMEOUT_SEC)}s timeout.")  # type: ignore[arg-type]
                        logger.error("tree_worker_timeout", job_id=jid, domain=dom, timeout_sec=WORKER_TIMEOUT_SEC)
                    except Exception as exc:
                        from app.core.types import StepResult
                        res = StepResult.fail(type(exc).__name__, f"{type(exc).__name__}: {exc}")  # type: ignore[arg-type]
                        logger.error("tree_worker_exception", job_id=jid, domain=dom, error=f"{type(exc).__name__}: {exc}")
                    async with lock:
                        if res.ok:
                            data = res.data
                            strat = data.get("strategy", "TREE_DFS")
                            hops = int(data.get("hops", 0))
                            prof_cnt = int(data.get("candidate_profile_count", 0))
                            tree_doc = data.get("tree")
                            mapped_cnt = len(tree_doc.departments_map) if tree_doc else 0

                            rosters_verified += 1
                            total_hops += hops
                            departments_mapped += mapped_cnt
                            if strat == "TREE_DFS":
                                bfs_dfs_wins += 1
                            elif strat == "SERPER_LLM_FALLBACK":
                                serper_fallback_wins += 1
                            elif strat == "TREE_CACHE":
                                cache_wins += 1

                            job.university_details[dom].update({
                                "winning_strategy": strat,
                                "nav_type": tree_doc.nav_type if tree_doc else "UNKNOWN",
                                "departments_mapped_count": mapped_cnt,
                                "token_stats": tree_doc.token_stats if tree_doc else {},
                                "faculty_roster_url": data["roster_url"],
                                "department_url": data.get("department_url"),
                                "professors_found": prof_cnt,
                                "professors_verified": 0,
                                "status": "COMPLETE",
                                "error_code": None,
                                "detail": f"Verified roster ({prof_cnt} candidate links, {hops} hops, {mapped_cnt} depts mapped)",
                            })
                            await repo.upsert_department_doc(
                                UniversityDeptDoc(
                                    domain=dom,
                                    department=department,
                                    degree=degree,  # type: ignore[arg-type]
                                    department_url=data.get("department_url") or data["roster_url"],
                                    faculty_roster_url=data["roster_url"],
                                    winning_strategy=strat,
                                    status="COMPLETE",
                                )
                            )
                        else:
                            failures += 1
                            job.university_details[dom].update({
                                "winning_strategy": "NONE",
                                "status": "NEEDS_REVIEW",
                                "error_code": res.error_code,
                                "detail": res.detail or "",
                            })
                            job.errors.append({"domain": dom, "stage": "tree_build", "error_code": res.error_code, "detail": res.detail})

                        if dom not in job.completed_domains:
                            job.completed_domains.append(dom)

                        avg_hops = round(total_hops / rosters_verified, 2) if rosters_verified else 0.0
                        job.scorecard = {
                            "mode": "TREE_ONLY",
                            "rosters_verified": rosters_verified,
                            "avg_hops": avg_hops,
                            "departments_mapped": departments_mapped,
                            "bfs_dfs_wins": bfs_dfs_wins,
                            "serper_fallback_wins": serper_fallback_wins,
                            "cache_wins": cache_wins,
                            "failures": failures,
                            "winning_strategies": {
                                "TREE_DFS": bfs_dfs_wins,
                                "SERPER_LLM_FALLBACK": serper_fallback_wins,
                                "TREE_CACHE": cache_wins,
                            },
                        }
                        await repo.upsert_job(job)
                finally:
                    current_domain.reset(dom_token)
                    queue.task_done()

        workers = min(max(1, admin.max_concurrent_universities), max(1, queue.qsize()))
        await asyncio.gather(*[_worker() for _ in range(workers)])

        job.status = "COMPLETED"
        job.completed_at = utc_now()
        await repo.upsert_job(job)
        logger.info("tree_job_completed", job_id=jid, scorecard=job.scorecard)
        return job
    finally:
        current_job_id.reset(job_token)


@router.post("/build")
async def build_trees_endpoint(body: BuildTreesRequest, request: Request):
    """Runs ONLY the Tree Builder + Deterministic Roster Verification Gate across matched universities."""
    repo: Repository = request.app.state.repo
    admin: AdminConfig = request.app.state.admin_config
    builder: SiteTreeBuilder = request.app.state.tree_builder

    tier_lim = parse_tier_limit(body.tier)
    eff_limit = min(tier_lim, admin.max_universities_per_job) if tier_lim is not None else admin.max_universities_per_job

    seeds = await filter_university_seeds(
        repo.db,
        country=body.country,
        regions=body.regions,
        tier=body.tier,
        limit=eff_limit,
    )
    domains = [s.domain for s in seeds]
    job_id = f"tree_{uuid.uuid4().hex[:8]}"
    uni_details = {
        s.domain: {
            "domain": s.domain,
            "name": s.name,
            "chinese_name": s.chinese_name,
            "region": s.region,
            "rank": s.rank,
            "winning_strategy": "PENDING",
            "faculty_roster_url": None,
            "department_url": None,
            "professors_found": 0,
            "professors_verified": 0,
            "status": "QUEUED",
            "error_code": None,
            "detail": "",
        }
        for s in seeds
    }
    job = JobDoc(
        job_id=job_id,
        request=body.model_dump(),
        status="QUEUED",
        target_domains=domains,
        university_details=uni_details,
        scorecard={"mode": "TREE_ONLY", "rosters_verified": 0, "avg_hops": 0.0, "departments_mapped": 0, "bfs_dfs_wins": 0, "serper_fallback_wins": 0, "failures": 0},
    )
    await repo.upsert_job(job)

    if body.run_sync:
        done = await _run_tree_build_job(repo, builder, admin, job, body.department, body.degree, body.force_refresh)
        return {
            "source": "job",
            "job_id": done.job_id,
            "status": done.status,
            "target_domains": done.target_domains,
            "university_details": done.university_details,
            "scorecard": done.scorecard,
        }

    asyncio.create_task(_run_tree_build_job(repo, builder, admin, job, body.department, body.degree, body.force_refresh))
    return {
        "source": "job",
        "job_id": job_id,
        "status": "QUEUED",
        "target_domains": domains,
        "university_details": uni_details,
    }


async def _run_tree_extract_job(
    repo: Repository,
    scraper: Phase2ScraperService,
    extractor: Phase2ExtractorService,
    admin: AdminConfig,
    job: JobDoc,
    roster_map: dict[str, dict[str, Any]],
    department: str,
    degree: str,
    force_reextract: bool = False,
) -> JobDoc:
    """Step 2 Batch Executor: runs Phase 2A + Phase 2B with adaptive 5->1 backpressure and $0 skip for already-verified professors."""
    jid = job.job_id
    job_token = current_job_id.set(jid)
    try:
        job.status = "RUNNING"
        job.queue_mode = llm_router.queue_mode
        job.active_concurrency = min(max(1, admin.max_concurrent_universities), max(1, llm_router.active_concurrency))
        await repo.upsert_job(job)
        logger.info("tree_extract_job_started", job_id=jid, target_count=len(job.target_domains), department=department, degree=degree, force_reextract=force_reextract)

        lock = asyncio.Lock()
        queue: asyncio.Queue[str] = asyncio.Queue()
        for d in job.target_domains:
            queue.put_nowait(d)

        active_workers = 0
        slot_cond = asyncio.Condition()

        async def _worker() -> None:
            nonlocal active_workers
            while not queue.empty():
                async with slot_cond:
                    while active_workers >= min(max(1, admin.max_concurrent_universities), max(1, llm_router.active_concurrency)):
                        await slot_cond.wait_for(lambda: active_workers < min(max(1, admin.max_concurrent_universities), max(1, llm_router.active_concurrency)))
                    try:
                        dom = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    active_workers += 1
                dom_token = current_domain.set(dom)
                try:
                    meta = roster_map[dom]
                    roster_url = meta["roster_url"]
                    dept_url = meta.get("department_url") or roster_url
                    win_strat = meta.get("strategy", "TREE_CACHE")
                    job.university_details[dom]["status"] = "RUNNING"
                    logger.info("tree_extract_uni_started", job_id=jid, domain=dom, roster_url=roster_url)

                    uni_found = 0
                    uni_verified = 0
                    uni_attempts = 0
                    uni_skipped = 0
                    uni_err: dict[str, Any] | None = None
                    canary_alert: dict[str, Any] | None = None

                    async def _extract_one_uni() -> None:
                        nonlocal uni_found, uni_verified, uni_attempts, uni_skipped, uni_err, canary_alert
                        crawl_res = await scraper.crawl_roster_urls(roster_url)
                        if not crawl_res.ok:
                            uni_err = {"domain": dom, "stage": "phase2_crawl", "error_code": crawl_res.error_code, "detail": crawl_res.detail}
                            logger.warning("phase2_crawl_failed", job_id=jid, domain=dom, error_code=crawl_res.error_code, detail=crawl_res.detail)
                            return

                        prof_urls = crawl_res.data["profile_urls"]
                        roster_title = crawl_res.data.get("roster_title", "")
                        roster_mode = crawl_res.data.get("roster_mode", "BIO_LINKS")
                        inline_snap = crawl_res.data.get("inline_snapshot")
                        uni_found = len(prof_urls)
                        logger.info("phase2_crawl_done", job_id=jid, domain=dom, profiles_found=uni_found, roster_mode=roster_mode)

                        if roster_mode == "INLINE_TABLE" and inline_snap is not None:
                            profs = await extractor.extract_inline_table_professors(
                                inline_snap, department=department, source_roster_url=roster_url, roster_title=roster_title
                            )
                            uni_found = max(uni_found, len(profs))
                            uni_attempts += max(1, len(profs))
                            uni_verified += len(profs)
                            return

                        canary_checked = False
                        for prof_url in prof_urls:
                            # $0 Resume: skip already-VERIFIED professors unless force_reextract=True
                            if not force_reextract:
                                existing_p = await repo.get_professor_by_url(prof_url)
                                if existing_p and existing_p.grounding_status == "VERIFIED":
                                    uni_verified += 1
                                    uni_skipped += 1
                                    continue

                            snap_res = await scraper.fetch_and_snapshot_profile(prof_url, dom)
                            if not snap_res.ok:
                                logger.warning("phase2_snapshot_failed", job_id=jid, domain=dom, url=prof_url, error_code=snap_res.error_code)
                                continue
                            uni_attempts += 1
                            ext_res = await extractor.extract_from_snapshot(
                                snap_res.data, department=department, source_roster_url=roster_url, roster_title=roster_title
                            )
                            if ext_res.ok:
                                uni_verified += 1
                            else:
                                logger.warning("phase2_extract_rejected", job_id=jid, domain=dom, url=prof_url, error_code=ext_res.error_code, detail=ext_res.detail)
                                if not canary_checked and len(prof_urls) > 3 and is_canary_sentinel_mismatch(ext_res.error_code, ext_res.detail or ""):
                                    canary_alert = {
                                        "domain": dom,
                                        "stage": "phase2_canary",
                                        "error_code": "CANARY_VALIDATION_ALERT",
                                        "detail": f"Canary prof #1 ({prof_url}) failed with internal sentinel mismatch: {ext_res.detail}",
                                    }
                                    uni_err = canary_alert
                                    logger.error("canary_validation_alert", job_id=jid, domain=dom, url=prof_url, detail=ext_res.detail)
                                    break
                            canary_checked = True

                    try:
                        await asyncio.wait_for(_extract_one_uni(), timeout=WORKER_TIMEOUT_SEC)
                    except asyncio.TimeoutError:
                        uni_err = {
                            "domain": dom,
                            "stage": "worker_timeout",
                            "error_code": "WORKER_TIMEOUT",
                            "detail": f"Extraction worker exceeded {int(WORKER_TIMEOUT_SEC)}s timeout.",
                        }
                        logger.error("tree_extract_worker_timeout", job_id=jid, domain=dom, timeout_sec=WORKER_TIMEOUT_SEC)
                    except Exception as exc:
                        uni_err = {
                            "domain": dom,
                            "stage": "worker_exception",
                            "error_code": type(exc).__name__,
                            "detail": f"{type(exc).__name__}: {exc}",
                        }
                        logger.error("tree_extract_worker_exception", job_id=jid, domain=dom, error=f"{type(exc).__name__}: {exc}")

                    row_status = "COMPLETE" if uni_verified > 0 else "NEEDS_REVIEW"
                    if uni_verified == 0 and not uni_err:
                        uni_err = {
                            "domain": dom,
                            "stage": "phase2_verify",
                            "error_code": "ZERO_VERIFIED_PROFESSORS",
                            "detail": f"Extracted 0 verified professors from {uni_found} links.",
                        }

                    await repo.upsert_department_doc(
                        UniversityDeptDoc(
                            domain=dom,
                            department=department,
                            degree=degree,  # type: ignore[arg-type]
                            department_url=dept_url,
                            faculty_roster_url=roster_url,
                            winning_strategy=win_strat,
                            status=row_status,  # type: ignore[arg-type]
                            error_code=uni_err["error_code"] if uni_err else None,
                        )
                    )

                    async with lock:
                        if canary_alert:
                            job.scorecard["canary_validation_alert"] = canary_alert
                        job.queue_mode = llm_router.queue_mode
                        job.active_concurrency = min(max(1, admin.max_concurrent_universities), max(1, llm_router.active_concurrency))
                        job.scorecard["mode"] = "TREE_EXTRACT"
                        job.scorecard["grounding_attempts"] = job.scorecard.get("grounding_attempts", 0) + uni_attempts
                        job.scorecard["grounding_passed"] = job.scorecard.get("grounding_passed", 0) + (uni_verified - uni_skipped)
                        attempts = job.scorecard["grounding_attempts"]
                        passed = job.scorecard["grounding_passed"]
                        job.scorecard["grounding_pass_pct"] = round((passed / attempts) * 100.0, 2) if attempts else 100.0
                        job.scorecard["total_verified_professors"] = job.scorecard.get("total_verified_professors", 0) + uni_verified
                        job.scorecard["skipped_cached_professors"] = job.scorecard.get("skipped_cached_professors", 0) + uni_skipped
                        if uni_err:
                            job.errors.append(uni_err)
                            job.scorecard["failures"] = job.scorecard.get("failures", 0) + 1

                        job.university_details[dom].update({
                            "winning_strategy": win_strat,
                            "faculty_roster_url": roster_url,
                            "department_url": dept_url,
                            "professors_found": uni_found,
                            "professors_verified": uni_verified,
                            "status": row_status,
                            "error_code": uni_err["error_code"] if uni_err else None,
                            "detail": uni_err["detail"] if uni_err else f"Verified {uni_verified} professors ({uni_skipped} cached)",
                        })
                        if dom not in job.completed_domains:
                            job.completed_domains.append(dom)
                        await repo.upsert_job(job)
                        logger.info("tree_extract_uni_done", job_id=jid, domain=dom, status=row_status, professors_verified=uni_verified, skipped_cached=uni_skipped)
                finally:
                    current_domain.reset(dom_token)
                    queue.task_done()
                    async with slot_cond:
                        active_workers = max(0, active_workers - 1)
                        slot_cond.notify_all()

        workers = min(max(1, admin.max_concurrent_universities), max(1, queue.qsize()))
        await asyncio.gather(*[_worker() for _ in range(workers)])

        job.status = "COMPLETED"
        job.completed_at = utc_now()
        await repo.upsert_job(job)
        logger.info("tree_extract_job_completed", job_id=jid, scorecard=job.scorecard)
        return job
    finally:
        current_job_id.reset(job_token)


@router.post("/extract")
async def extract_from_trees_endpoint(body: ExtractFromTreesRequest, request: Request):
    """Step 2 Batch Execution: runs Phase 2A + Phase 2B extraction across all matched universities with saved verified_rosters."""
    repo: Repository = request.app.state.repo
    admin: AdminConfig = request.app.state.admin_config
    scraper: Phase2ScraperService = request.app.state.scraper
    extractor: Phase2ExtractorService = request.app.state.extractor

    tier_lim = parse_tier_limit(body.tier)
    eff_limit = min(tier_lim, admin.max_universities_per_job) if tier_lim is not None else admin.max_universities_per_job

    seeds = await filter_university_seeds(
        repo.db,
        country=body.country,
        regions=body.regions,
        tier=body.tier,
        limit=eff_limit,
    )
    roster_key = f"{body.department.strip()}::{body.degree}"
    dept_prefix = f"{body.department.strip().lower()}::"

    roster_map: dict[str, dict[str, Any]] = {}
    matched_seeds = []
    for s in seeds:
        t = await repo.get_site_tree(s.domain)
        if not t or not t.verified_rosters:
            continue
        entry = t.verified_rosters.get(roster_key)
        if entry is None:
            for k, v in t.verified_rosters.items():
                if k.lower().startswith(dept_prefix):
                    entry = v
                    break
        if entry is not None:
            matched_seeds.append(s)
            roster_map[s.domain] = {
                "roster_url": entry.roster_url,
                "department_url": entry.department_url,
                "strategy": entry.strategy,
                "nav_type": t.nav_type,
                "departments_mapped_count": len(t.departments_map),
            }

    if not matched_seeds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No universities with saved verified_rosters found for '{body.department}' ({body.degree}). Run Step 1 (Build & Verify Trees) first.",
        )

    domains = [s.domain for s in matched_seeds]
    job_id = f"ext_{uuid.uuid4().hex[:8]}"
    uni_details = {
        s.domain: {
            "domain": s.domain,
            "name": s.name,
            "chinese_name": s.chinese_name,
            "region": s.region,
            "rank": s.rank,
            "nav_type": roster_map[s.domain]["nav_type"],
            "departments_mapped_count": roster_map[s.domain]["departments_mapped_count"],
            "winning_strategy": roster_map[s.domain]["strategy"],
            "faculty_roster_url": roster_map[s.domain]["roster_url"],
            "department_url": roster_map[s.domain]["department_url"],
            "professors_found": 0,
            "professors_verified": 0,
            "status": "QUEUED",
            "error_code": None,
            "detail": "",
        }
        for s in matched_seeds
    }
    job = JobDoc(
        job_id=job_id,
        request=body.model_dump(),
        status="QUEUED",
        target_domains=domains,
        university_details=uni_details,
        scorecard={
            "mode": "TREE_EXTRACT",
            "grounding_attempts": 0,
            "grounding_passed": 0,
            "grounding_pass_pct": 100.0,
            "total_verified_professors": 0,
            "failures": 0,
        },
    )
    await repo.upsert_job(job)

    if body.run_sync:
        done = await _run_tree_extract_job(
            repo, scraper, extractor, admin, job, roster_map, body.department, body.degree, force_reextract=body.force_reextract
        )
        return {
            "source": "job",
            "job_id": done.job_id,
            "status": done.status,
            "target_domains": done.target_domains,
            "university_details": done.university_details,
            "scorecard": done.scorecard,
        }

    asyncio.create_task(
        _run_tree_extract_job(
            repo, scraper, extractor, admin, job, roster_map, body.department, body.degree, force_reextract=body.force_reextract
        )
    )
    return {
        "source": "job",
        "job_id": job_id,
        "status": "QUEUED",
        "target_domains": domains,
        "university_details": uni_details,
    }


@router.get("")
async def list_trees_endpoint(request: Request):
    """Lists all saved university site trees with summary statistics."""
    repo: Repository = request.app.state.repo
    trees = await repo.list_site_trees()
    return [
        {
            "domain": t.domain,
            "root_url": t.root_url,
            "nav_type": t.nav_type,
            "departments_mapped_count": len(t.departments_map),
            "verified_rosters_count": len(t.verified_rosters),
            "nodes_count": len(t.nodes),
            "token_stats": t.token_stats,
            "updated_at": t.updated_at.isoformat(),
        }
        for t in trees
    ]


@router.get("/{domain}")
async def get_tree_by_domain(domain: str, request: Request):
    """Returns the saved markdown_tree, departments_map, navigation_trail, token_stats, and verified_rosters."""
    repo: Repository = request.app.state.repo
    tree = await repo.get_site_tree(domain)
    if not tree:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No site tree saved for '{domain}'.")
    return {
        "domain": tree.domain,
        "root_url": tree.root_url,
        "nav_type": tree.nav_type,
        "markdown_tree": tree.markdown_tree,
        "departments_map": tree.departments_map,
        "verified_rosters": {k: v.model_dump(mode="json") for k, v in tree.verified_rosters.items()},
        "navigation_trail": tree.navigation_trail,
        "token_stats": tree.token_stats,
        "updated_at": tree.updated_at.isoformat(),
    }
