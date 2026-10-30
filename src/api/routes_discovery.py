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


@router.post("/filter", response_model=List[University])
async def filter_universities_endpoint(request: FilterUniversitiesRequest, user: str = Depends(get_current_user)):
    """Filters Chinese universities dynamically by Region, Tier/Rank, and attaches CS/AI department endpoints."""
    matched = discovery_engine.filter_universities(
        regions=request.regions,
        tiers=request.tiers,
        max_rank=request.max_rank,
        keyword=request.keyword
    )
    for u in matched:
        u.department_endpoints = discovery_engine.discover_department_endpoints(u, request.discipline)
        if db_manager.is_connected and db_manager.db is not None:
            try:
                await db_manager.get_collection("universities").update_one(
                    {"domain": u.domain},
                    {"$set": u.model_dump()},
                    upsert=True
                )
            except Exception:
                pass
    return matched


from src.core.database import db_manager


@router.get("/universities", response_model=List[University])
async def get_universities_directory(user: str = Depends(get_current_user)):
    """Returns directory of known universities strictly from MongoDB database without auto-seeding."""
    if db_manager.is_connected and db_manager.db is not None:
        cursor = db_manager.get_collection("universities").find({})
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(University(**doc))
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

