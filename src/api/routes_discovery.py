"""Discovery, feasibility evaluation, and pre-run cost estimation endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.models.university import (
    DepartmentEndpoint,
    PreRunCostEstimate,
    University,
)
from src.services.discovery import (
    discovery_engine,
)

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
                    await db_manager.get_collection("universities").update_one(
                        {"domain": updated_univ.domain},
                        {"$set": updated_univ.model_dump()},
                        upsert=True
                    )
                except Exception:
                    pass
            return updated_univ

    resolved_list = await asyncio.gather(*[_probe_single_domain(dom) for dom in request.domains])
    return list(resolved_list)


from src.core.database import db_manager


@router.get("/universities", response_model=List[University])
async def get_universities_directory(user: str = Depends(get_current_user)):
    """Returns directory of known Master's-granting universities strictly from MongoDB database (deduplicated)."""
    from src.services.discovery import VOCATIONAL_EXCLUSION_EN, VOCATIONAL_EXCLUSION_ZH

    if db_manager.is_connected and db_manager.db is not None:
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
            # Clean up any legacy 4-part subdomain entries (e.g. ar.shisu.edu.cn, en.bjtu.edu.cn)
            parts = [p for p in dom.split(".") if p]
            if len(parts) > 3:
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
        return results

    # Offline/disconnected fallback returns empty list
    return []


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

