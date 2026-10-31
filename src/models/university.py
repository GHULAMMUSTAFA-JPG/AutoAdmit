"""University and discovery Pydantic schemas (all records originate from live internet sources)."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class FeasibilityTier(str, Enum):
    """Rank category derived from live Project 985 / 211 membership data."""
    TIER_1_DREAM = "Tier 1 (Dream)"      # Project 985 member
    TIER_2_TARGET = "Tier 2 (Target)"    # Project 211 member (non-985)
    TIER_3_SAFETY = "Tier 3 (Safety)"    # Other accredited institution


class ScholarshipType(str, Enum):
    CSC_TYPE_B = "CSC Type B (Full Funding)"
    PROVINCIAL = "Provincial Government Scholarship"
    PRESIDENTIAL = "University Presidential Scholarship"
    BELT_AND_ROAD = "Silk Road / Belt and Road Grant"


class DepartmentEndpoint(BaseModel):
    name: str = Field(..., description="Department or School name as published on the university site")
    url: str = Field(..., description="Verified faculty directory URL on an official .edu.cn domain")
    is_verified: bool = Field(default=False, description="True only when confirmed via live homepage/HTTP check")
    status: str = Field(default="Pending Verification", description="Verification state of this endpoint")


class University(BaseModel):
    id: Optional[str] = None
    wikidata_id: Optional[str] = Field(default=None, description="Wikidata entity id (live source lineage)")
    name: str = Field(..., description="English Name of University")
    chinese_name: Optional[str] = Field(default=None, description="Native Chinese name")
    domain: str = Field(..., description="Official educational domain e.g. tsinghua.edu.cn")
    website: Optional[str] = Field(default=None, description="Official website URL from the live source")
    region: str = Field(default="Unknown", description="Province-level region resolved from live data")
    tier: FeasibilityTier = Field(default=FeasibilityTier.TIER_3_SAFETY)
    cs_ranking: Optional[int] = Field(default=None, description="Unset: no live ranking source configured")
    is_project_985: bool = Field(default=False)
    is_project_211: bool = Field(default=False)
    is_double_first_class: bool = Field(default=False)
    scholarships_available: List[ScholarshipType] = Field(default_factory=list)
    application_fee_rmb: Optional[int] = Field(default=None, description="Unknown unless scraped; never assumed")
    fee_note: str = Field(default="400–800 RMB (Standard Est.)", description="Realistic application fee guidance")
    feasibility_notes: str = Field(default="")
    pipeline_status: str = Field(default="Pending Live Check", description="Current discovery/extraction status")
    status_reason: Optional[str] = Field(default="Not live-probed yet. Click 'Verify & Find Dept' or 'Resolve Real Dept Links' to run live check.", description="Detailed diagnostic reason for current pipeline_status")
    department_endpoints: List[DepartmentEndpoint] = Field(default_factory=list)
    website_verified: bool = Field(default=False, description="True only when official site is live-fetched & confirmed")
    verified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    is_seed: bool = Field(default=False)
    data_source: str = Field(default="wikidata_live")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreRunCostEstimate(BaseModel):
    total_target_departments: int
    estimated_pages_to_crawl: int
    estimated_faculty_count: int
    estimated_gemini_tokens: int
    estimated_runtime_seconds: int
    is_approved: bool = False
    approved_at: Optional[datetime] = None
