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
    KNOWN_UNIVERSITIES_METADATA,
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


@router.get("/universities", response_model=List[University])
def get_universities_directory(user: str = Depends(get_current_user)):
    """Returns directory of known universities with scholarship metadata and feasibility tiers."""
    results = []
    for domain, meta in KNOWN_UNIVERSITIES_METADATA.items():
        univ = discovery_engine.assess_university(domain)
        results.append(univ)
    return results


@router.post("/feasibility", response_model=List[University])
def evaluate_feasibility(request: IntakeRequest, user: str = Depends(get_current_user)):
    """Evaluates institutional competitiveness against profile realities (2.68 CGPA compensation)."""
    results = []
    for url in request.urls:
        univ = discovery_engine.assess_university(url)
        results.append(univ)
        discovered_universities_cache[univ.id] = univ
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

