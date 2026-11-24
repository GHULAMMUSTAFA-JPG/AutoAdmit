"""Tree-Only Discovery & Verification endpoints (`POST /api/v1/trees/build`, `GET /api/v1/trees`, `GET /api/v1/trees/{domain}`)."""

import asyncio
from typing import Any, Literal
import uuid
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.logging import current_domain, current_job_id, get_logger
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, UniversityDeptDoc, utc_now
from app.schemas.filters import AdminConfig, parse_tier_limit
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
                    res = await builder.build_and_find_roster(dom, department, degree, force_refresh=force_refresh)
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


@router.get("")
async def list_trees_endpoint(request: Request):
    """Lists all saved university site trees with summary statistics."""
    repo: Repository = request.app.state.repo
    trees = await repo.list_site_trees()
    return [
        {
            "domain": t.domain,
            "root_url": t.root_url,
            "departments_mapped_count": len(t.departments_map),
            "verified_rosters_count": len(t.verified_rosters),
            "nodes_count": len(t.nodes),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in trees
    ]


@router.get("/{domain}")
async def get_tree_by_domain(domain: str, request: Request):
    """Returns the saved markdown_tree, departments_map, and verified_rosters for a university domain."""
    repo: Repository = request.app.state.repo
    tree = await repo.get_site_tree(domain)
    if not tree:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No site tree saved for '{domain}'.")
    return {
        "domain": tree.domain,
        "root_url": tree.root_url,
        "markdown_tree": tree.markdown_tree,
        "departments_map": tree.departments_map,
        "verified_rosters": {k: v.model_dump(mode="json") for k, v in tree.verified_rosters.items()},
        "updated_at": tree.updated_at.isoformat(),
    }
