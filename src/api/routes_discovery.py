"""Discovery, feasibility evaluation, and pre-run cost estimation endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.core.logger import setup_logger
from src.core.policies import policy_manager
from src.core.telemetry import JobScorecard, TerminalStatus
from src.models.university import (
    DepartmentEndpoint,
    Phase1JobProgress,
    Phase1JobRecord,
    PreRunCostEstimate,
    University,
    UniversityDepartmentCache,
)
from src.services.discovery import (
    discovery_engine,
)

logger = setup_logger("DiscoveryAPI")

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])

# In-memory store for active discovery sessions
active_estimates: dict = {}
discovered_universities_cache: dict = {}


class IntakeRequest(BaseModel):
    urls: List[str]
    applicant_cgpa: float = 2.68
    primary_skills: List[str] = ["Python", "PyTorch", "Agentic AI", "Computer Vision"]


class FilterUniversitiesRequest(BaseModel):
    regions: Optional[List[str]] = None
    tiers: Optional[List[str]] = None
    max_rank: Optional[int] = None
    discipline: str = "Computer Science"
    keyword: Optional[str] = None
    source: str = "combined"


class ResolveDepartmentsRequest(BaseModel):
    domains: List[str]
    discipline: str = "Computer Science"
    max_workers: int = 3


@router.post("/filter", response_model=List[University])
async def filter_universities_endpoint(request: FilterUniversitiesRequest, user: str = Depends(get_current_user)):
    """
    1. Queries live sources ('combined', 'wikidata', 'moe').
    2. Persists the Raw Multi-Source vs. Normalized Audit to MongoDB ('discovery_runs').
    3. Saves all normalized universities to MongoDB ('universities') while preserving live-verified states.
    4. Reads the persisted records back from MongoDB and returns them to the UI.
    """
    matched = discovery_engine.filter_universities(
        regions=request.regions,
        tiers=request.tiers,
        max_rank=request.max_rank,
        keyword=request.keyword,
        source=request.source
    )
    matched_domains = []
    for u in matched:
        matched_domains.append(u.domain)
        if not u.department_endpoints:
            u.department_endpoints = discovery_engine.discover_department_endpoints(u, request.discipline)
        if db_manager.is_connected and db_manager.db is not None:
            try:
                existing = await db_manager.get_collection("universities").find_one({"domain": u.domain})
                if existing and existing.get("pipeline_status") in (
                    "Homepage Verified", "Department URL Found", "Faculty Page Found",
                    "Professor Extraction Completed", "Homepage OK · Dept Not Found",
                    "Department URL Not Found", "Requires Manual Review", "Step 1 Failed: Homepage Unreachable"
                ) and (existing.get("verified_at") or existing.get("status_reason")):
                    u.pipeline_status = existing["pipeline_status"]
                    u.status_reason = existing.get("status_reason") or u.status_reason
                    u.website_verified = bool(existing.get("website_verified"))
                    u.verified_at = existing.get("verified_at")
                    u.resolved_at = existing.get("resolved_at")
                    if existing.get("department_endpoints"):
                        u.department_endpoints = [DepartmentEndpoint(**ep) for ep in existing["department_endpoints"]]
                await db_manager.get_collection("universities").update_one(
                    {"domain": u.domain},
                    {"$set": u.model_dump()},
                    upsert=True
                )
            except Exception:
                pass

    # Persist the latest Raw vs. Normalized Discovery Run Audit to MongoDB
    audit_doc = getattr(discovery_engine, "last_discovery_audit", None)
    if audit_doc and db_manager.is_connected and db_manager.db is not None:
        try:
            await db_manager.get_collection("discovery_runs").update_one(
                {"id": "latest_run"},
                {"$set": {**audit_doc, "id": "latest_run", "matched_domains": matched_domains}},
                upsert=True
            )
        except Exception:
            pass

    # Read back from MongoDB so UI strictly displays DB-persisted truth (deduplicated by domain)
    if db_manager.is_connected and db_manager.db is not None and matched_domains:
        try:
            cursor = db_manager.get_collection("universities").find({"domain": {"$in": matched_domains}})
            db_results = []
            seen_db_domains = set()
            seen_db_names = set()
            async for doc in cursor:
                doc.pop("_id", None)
                dom = (doc.get("domain") or "").lower().strip()
                nm = (doc.get("name") or "").lower().strip()
                if dom in seen_db_domains or (nm and nm in seen_db_names):
                    continue
                seen_db_domains.add(dom)
                if nm:
                    seen_db_names.add(nm)
                db_results.append(discovery_engine.enrich_university_record(University(**doc)))
            if db_results:
                db_results.sort(key=lambda x: (x.region or "ZZZ", x.tier.value if x.tier else "Z", x.name))
                return db_results
        except Exception:
            pass

    return matched


@router.get("/last-audit")
async def get_last_discovery_audit(user: str = Depends(get_current_user)):
    """Returns the latest persisted Discovery Run Audit (Raw Multi-Source vs. Normalized Breakdown) from MongoDB."""
    if db_manager.is_connected and db_manager.db is not None:
        try:
            doc = await db_manager.get_collection("discovery_runs").find_one({"id": "latest_run"})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception:
            pass
    return getattr(discovery_engine, "last_discovery_audit", None) or {}


@router.post("/resolve-departments", response_model=List[University])
async def resolve_departments_endpoint(request: ResolveDepartmentsRequest, user: str = Depends(get_current_user)):
    """Executes Homepage-First Department & Supervisor Directory Discovery across target university domains (max 3 workers)."""
    import asyncio
    sem = asyncio.Semaphore(max(1, min(request.max_workers, 3)))

    async def _probe_single_domain(dom: str) -> University:
        async with sem:
            univ = None
            if db_manager.is_connected and db_manager.db is not None:
                try:
                    doc = await db_manager.get_collection("universities").find_one({"domain": dom})
                    if doc:
                        doc.pop("_id", None)
                        univ = University(**doc)
                except Exception:
                    pass
            if not univ:
                univ = discovery_engine.assess_university(dom)
                univ.department_endpoints = discovery_engine.discover_department_endpoints(univ, request.discipline)

            try:
                updated_univ = await discovery_engine.resolve_department_from_homepage(univ, request.discipline)
            except Exception as err:
                univ.pipeline_status = "Step 1 Failed: Homepage Unreachable"
                univ.status_reason = f"Unhandled probe error: {err}"
                updated_univ = univ

            if db_manager.is_connected and db_manager.db is not None:
                try:
                    import json
                    dump_data = json.loads(updated_univ.model_dump_json())
                    clean_dom = (updated_univ.domain or dom).lower().strip()
                    dump_data["domain"] = clean_dom
                    await db_manager.get_collection("universities").update_one(
                        {"domain": clean_dom},
                        {"$set": dump_data},
                        upsert=True
                    )
                except Exception as db_err:
                    logger.error(f"[{dom}] Failed to persist resolved university to MongoDB: {db_err}")
            return updated_univ

    resolved_list = await asyncio.gather(*[_probe_single_domain(dom) for dom in request.domains])
    return list(resolved_list)


from src.core.database import db_manager
import json
from pathlib import Path

SNAPSHOT_PATH = Path("data/universities_snapshot.json")

def _save_snapshot(universities: List[University]) -> None:
    try:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = [u.model_dump(mode="json") for u in universities]
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save universities snapshot: {e}")

def _load_snapshot() -> List[University]:
    try:
        if SNAPSHOT_PATH.exists():
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
                return [discovery_engine.enrich_university_record(University(**item)) for item in raw_list]
    except Exception as e:
        logger.warning(f"Failed to load universities snapshot: {e}")
    return []


@router.get("/universities", response_model=List[University])
async def get_universities_directory(user: str = Depends(get_current_user)):
    """Returns directory of known Master's-granting universities strictly from MongoDB database (deduplicated) with snapshot fallback."""
    from src.services.discovery import VOCATIONAL_EXCLUSION_EN, VOCATIONAL_EXCLUSION_ZH

    if db_manager.is_connected and db_manager.db is not None:
        try:
            cursor = db_manager.get_collection("universities").find({})
            results = []
            seen_domains = set()
            seen_names = set()
            stale_subdomain_ids = []
            async for doc in cursor:
                raw_id = doc.pop("_id", None)
                dom = (doc.get("domain") or "").lower().strip()
                if not dom.endswith(".edu.cn") and not dom.endswith(".ac.cn"):
                    continue
                parts = [p for p in dom.split(".") if p]
                if len(parts) > 3 and not dom.startswith("www."):
                    if raw_id:
                        stale_subdomain_ids.append(raw_id)
                    continue
                en_low = (doc.get("name") or "").lower().strip()
                zh_low = (doc.get("chinese_name") or "").lower().strip()
                if any(v in zh_low for v in VOCATIONAL_EXCLUSION_ZH) or any(v in en_low for v in VOCATIONAL_EXCLUSION_EN):
                    continue
                if dom in seen_domains or (en_low and en_low in seen_names):
                    if raw_id:
                        stale_subdomain_ids.append(raw_id)
                    continue
                seen_domains.add(dom)
                if en_low:
                    seen_names.add(en_low)
                u = discovery_engine.enrich_university_record(University(**doc))
                results.append(u)

            if stale_subdomain_ids:
                try:
                    await db_manager.get_collection("universities").delete_many({"_id": {"$in": stale_subdomain_ids}})
                except Exception:
                    pass
            if results:
                _save_snapshot(results)
                return results
        except Exception as db_err:
            logger.warning(f"MongoDB query failed in /universities: {db_err}")

    # Fallback Layer 2: Persistent local snapshot
    snapshot = _load_snapshot()
    if snapshot:
        return snapshot

    # Fallback Layer 3: Built-in 705 genuine institutions registry
    fallback_records = discovery_engine.filter_universities(regions=None, source="combined")
    for u in fallback_records:
        if not u.department_endpoints:
            u.department_endpoints = discovery_engine.discover_department_endpoints(u, "Computer Science")
    _save_snapshot(fallback_records)
    return fallback_records


@router.post("/feasibility", response_model=List[University])
async def evaluate_feasibility(request: IntakeRequest, user: str = Depends(get_current_user)):
    """Evaluates institutional competitiveness against profile realities (2.68 CGPA compensation)."""
    results = []
    for url in request.urls:
        univ = discovery_engine.assess_university(url)
        results.append(univ)
        discovered_universities_cache[univ.id] = univ
        if db_manager.is_connected and db_manager.db is not None:
            try:
                await db_manager.get_collection("universities").update_one(
                    {"domain": univ.domain},
                    {"$set": univ.model_dump()},
                    upsert=True
                )
            except Exception:
                pass
    return results


@router.post("/estimate", response_model=PreRunCostEstimate)
def calculate_cost_gate(endpoints: List[DepartmentEndpoint], user: str = Depends(get_current_user)):
    """
    Pre-run cost and workload estimator.
    Execution halts in pending state until explicitly approved.
    """
    if not endpoints:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one target department endpoint is required."
        )

    estimate = discovery_engine.calculate_cost_estimate(endpoints)
    estimate_id = "default_session"
    active_estimates[estimate_id] = (estimate, endpoints)
    return estimate


@router.post("/approve", response_model=PreRunCostEstimate)
def approve_cost_gate(user: str = Depends(get_current_user)):
    """Unlocks hard confirmation gate for the pending discovery session."""
    estimate_id = "default_session"
    if estimate_id not in active_estimates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending cost estimate found. Calculate an estimate first."
        )

    estimate, endpoints = active_estimates[estimate_id]
    approved_estimate = discovery_engine.approve_estimate(estimate)
    active_estimates[estimate_id] = (approved_estimate, endpoints)
    return approved_estimate


# ------------------------------------------------------------------ Phase 1 Async Jobs, Scorecard & Review Queue
import asyncio
from datetime import datetime, timezone
import time
import uuid

phase1_jobs_store: dict[str, Phase1JobRecord] = {}


class CreatePhase1JobRequest(BaseModel):
    discipline: str = "Computer Science"
    disciplines: Optional[List[str]] = None
    degree: str = "master"
    top_n: int = 25
    regions: Optional[List[str]] = None
    tiers: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    force_refresh: bool = False
    run_sync: bool = False


class UpdatePolicyRequest(BaseModel):
    enable_search_api: Optional[bool] = None
    enable_playwright: Optional[bool] = None
    monthly_search_cap: Optional[int] = None
    reset_search_counter: bool = False


async def _persist_job(job: Phase1JobRecord) -> None:
    phase1_jobs_store[job.job_id] = job
    if db_manager.is_connected and db_manager.db is not None:
        payload = json.loads(job.model_dump_json())
        await db_manager.get_collection("phase1_jobs").update_one(
            {"job_id": job.job_id},
            {"$set": payload},
            upsert=True,
        )


async def _execute_phase1_job(
    job_id: str,
    target_universities: List[University],
    target_disciplines: List[str],
    force_refresh: bool,
) -> None:
    job = phase1_jobs_store[job_id]
    job.status = "RUNNING"
    await _persist_job(job)

    total_tasks = len(target_universities) * len(target_disciplines)
    scorecard = JobScorecard(job_id=job_id, target_universities=total_tasks)
    t_job_start = time.monotonic()

    sem = asyncio.Semaphore(5)

    async def _process_one(univ: University, disc: str) -> None:
        async with sem:
            rec = await discovery_engine.discover_department_4layer(
                university=univ,
                discipline=disc,
                trace_id=job_id,
                force_refresh=force_refresh,
                scorecard=scorecard,
            )
            job.results.append(rec)
            job.progress.processed += 1
            if rec.status in (TerminalStatus.COMPLETE.value, TerminalStatus.PARTIAL.value):
                job.progress.succeeded += 1
            else:
                job.progress.failed += 1
            scorecard.total_duration_sec = time.monotonic() - t_job_start
            job.scorecard = scorecard.to_dict()
            # Checkpoint after every completed (university, discipline)
            await _persist_job(job)

    tasks = [
        _process_one(u, d)
        for u in target_universities
        for d in target_disciplines
    ]
    await asyncio.gather(*tasks)

    scorecard.total_duration_sec = time.monotonic() - t_job_start
    job.scorecard = scorecard.to_dict()
    job.status = "COMPLETED"
    job.completed_at = datetime.now(timezone.utc)
    await _persist_job(job)


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_discovery_job(request: CreatePhase1JobRequest, user: str = Depends(get_current_user)):
    """
    Launches an asynchronous Phase 1 Discovery Job with bounded concurrency, per-domain rate limiting,
    entity-level TTL caching, checkpointing, and a self-measuring Run Scorecard.
    """
    target_disciplines = [d.strip() for d in (request.disciplines or [request.discipline]) if d and d.strip()]
    if not target_disciplines:
        target_disciplines = ["Computer Science"]

    if request.domains:
        target_universities = [discovery_engine.assess_university(dom) for dom in request.domains]
    else:
        matched = discovery_engine.filter_universities(
            regions=request.regions,
            tiers=request.tiers,
            source="combined",
        )
        # Rank by subject_rankings (if available), then tier
        matched.sort(key=lambda u: (u.cs_ranking if u.cs_ranking is not None else 999, u.name))
        target_universities = matched[: max(1, min(request.top_n, 100))]

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    total_tasks = len(target_universities) * len(target_disciplines)
    job = Phase1JobRecord(
        job_id=job_id,
        query_params={
            "disciplines": target_disciplines,
            "degree": request.degree,
            "top_n": request.top_n,
            "regions": request.regions,
            "tiers": request.tiers,
            "domains": [u.domain for u in target_universities],
            "force_refresh": request.force_refresh,
        },
        status="QUEUED",
        progress=Phase1JobProgress(total=total_tasks, processed=0, succeeded=0, failed=0),
        scorecard=JobScorecard(job_id=job_id, target_universities=total_tasks).to_dict(),
    )
    await _persist_job(job)

    if request.run_sync:
        await _execute_phase1_job(job_id, target_universities, target_disciplines, request.force_refresh)
    else:
        asyncio.create_task(_execute_phase1_job(job_id, target_universities, target_disciplines, request.force_refresh))

    return {
        "job_id": job_id,
        "status": phase1_jobs_store[job_id].status,
        "target_universities": len(target_universities),
        "target_disciplines": target_disciplines,
        "total_tasks": total_tasks,
    }


@router.get("/jobs/{job_id}", response_model=Phase1JobRecord)
async def get_discovery_job(job_id: str, user: str = Depends(get_current_user)):
    """Returns live progress, checkpointed results, and scorecard for a Phase 1 Discovery Job."""
    if job_id in phase1_jobs_store:
        return phase1_jobs_store[job_id]
    if db_manager.is_connected and db_manager.db is not None:
        doc = await db_manager.get_collection("phase1_jobs").find_one({"job_id": job_id})
        if doc:
            doc.pop("_id", None)
            rec = Phase1JobRecord(**doc)
            phase1_jobs_store[job_id] = rec
            return rec
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")


@router.get("/jobs/{job_id}/scorecard")
async def get_discovery_job_scorecard(job_id: str, user: str = Depends(get_current_user)):
    """Returns the Self-Measuring Health & Quality Scorecard for a Phase 1 Discovery Job."""
    job = await get_discovery_job(job_id, user=user)
    return job.scorecard


@router.get("/review-queue", response_model=List[UniversityDepartmentCache])
async def get_discovery_review_queue(user: str = Depends(get_current_user)):
    """Returns all `NEEDS_REVIEW` (and `NOT_FOUND`) university department records with exact typed ErrorCode and discovery_path."""
    records: List[UniversityDepartmentCache] = []
    seen = set()

    if db_manager.is_connected and db_manager.db is not None:
        cursor = db_manager.get_collection("university_departments").find(
            {"status": {"$in": [TerminalStatus.NEEDS_REVIEW.value, TerminalStatus.NOT_FOUND.value]}}
        )
        async for doc in cursor:
            doc.pop("_id", None)
            rec = UniversityDepartmentCache(**doc)
            key = (rec.domain, rec.discipline_key)
            if key not in seen:
                seen.add(key)
                records.append(rec)

    for key, rec in discovery_engine._dept_cache_memory.items():
        if key not in seen and rec.status in (TerminalStatus.NEEDS_REVIEW.value, TerminalStatus.NOT_FOUND.value):
            seen.add(key)
            records.append(rec)

    return records


@router.get("/policies")
def get_discovery_policies(user: str = Depends(get_current_user)):
    """Returns active Phase 1 admin kill-switches and monthly Search API budget counters."""
    return policy_manager.to_dict()


@router.post("/policies")
def update_discovery_policies(request: UpdatePolicyRequest, user: str = Depends(get_current_user)):
    """Updates Phase 1 admin kill-switches (`enable_search_api`, `enable_playwright`) and monthly budget caps."""
    return policy_manager.update_policies(
        enable_search_api=request.enable_search_api,
        enable_playwright=request.enable_playwright,
        monthly_search_cap=request.monthly_search_cap,
        reset_search_counter=request.reset_search_counter,
    )


