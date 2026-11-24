"""User discovery filters, AdminConfig guardrails, and strict validation helper."""

import re
from typing import Literal
from fastapi import HTTPException, status
from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    """User-supplied query filters for Phase 1 & Phase 2 discovery."""
    country: str = Field(default="China")
    regions: list[str] = Field(default_factory=list, description="Empty list means entire country")
    departments: list[str] = Field(..., min_length=1, description="Target department names")
    degree: Literal["masters", "phd", "both"] = Field(..., description="Required target degree")
    tier: str | None = Field(default="top_10", description="top_10, top_25, top_50, or all")
    limit: int | None = Field(default=None, ge=1)


class AdminConfig(BaseModel):
    """Runtime backend guardrails and feature flags editable by admin."""
    max_departments_per_request: int = Field(default=1, ge=1)
    max_universities_per_job: int = Field(default=20, ge=1)
    max_professors_per_uni: int = Field(default=80, ge=1)
    max_concurrent_universities: int = Field(default=2, ge=1, le=8)
    allowed_countries: list[str] = Field(default_factory=lambda: ["China"])
    enable_serper: bool = Field(default=True)
    enable_playwright: bool = Field(default=True)
    enable_agent_fallback: bool = Field(default=True)
    enable_colab_bridge: bool = Field(default=True)
    enable_llm_extraction: bool = Field(default=True)


def parse_tier_limit(tier: str | None) -> int | None:
    """Converts tier strings like 'top_10' or 'top_5' to an integer limit, or None for 'all'."""
    if not tier or tier.strip().lower() == "all":
        return None
    m = re.fullmatch(r"top_(\d+)", tier.strip().lower())
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier '{tier}'. Expected 'top_<N>' (e.g. top_10, top_25, top_50) or 'all'.",
        )
    return int(m.group(1))


def validate_discovery_request(req: DiscoveryRequest, admin: AdminConfig) -> int:
    """
    Enforces AdminConfig guardrails against a user DiscoveryRequest.
    Returns the effective university limit capped by admin.max_universities_per_job.
    Raises HTTP 400 with a clear message if any guardrail is violated.
    """
    allowed = {c.strip().lower() for c in admin.allowed_countries}
    if req.country.strip().lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Country '{req.country}' is not allowed. Allowed countries: {admin.allowed_countries}.",
        )

    clean_depts = [d.strip() for d in req.departments if d and d.strip()]
    if not clean_depts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one non-empty department is required.",
        )

    if len(clean_depts) > admin.max_departments_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Too many departments requested ({len(clean_depts)}). "
                f"Maximum allowed per request is {admin.max_departments_per_request}."
            ),
        )

    tier_limit = parse_tier_limit(req.tier)
    requested_limit = req.limit if req.limit is not None else tier_limit
    if requested_limit is None:
        return admin.max_universities_per_job
    return min(requested_limit, admin.max_universities_per_job)
