"""University and discovery Pydantic schemas (all records originate from live internet sources)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
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
    cs_ranking: Optional[int] = Field(default=None, description="Subject-specific ranking from CSRankings / Shanghai Ranking")
    subject_rankings: Dict[str, int] = Field(default_factory=dict, description="Subject-wise rank table e.g. {'cs': 1, 'ai': 2}")
    scholarship_urls: Dict[str, str] = Field(default_factory=dict, description="CSC and International Office portal URLs")
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


class FacultyRosterEndpoint(BaseModel):
    """Faculty directory URL with inherited breadcrumb / degree context for Phase 2."""
    url: str
    label_zh: str = "师资队伍"
    inherited_degree: str = "master"


class UniversityDepartmentCache(BaseModel):
    """Entity-level cached department & faculty roster record in `university_departments` collection."""
    domain: str
    university_name: str
    discipline_key: str
    department_name_zh: Optional[str] = None
    department_name_en: Optional[str] = None
    department_url: Optional[str] = None
    homepage_url: Optional[str] = None
    faculty_roster_urls: List[FacultyRosterEndpoint] = Field(default_factory=list)
    status: str = Field(default="NEEDS_REVIEW", description="COMPLETE | PARTIAL | NOT_FOUND | NEEDS_REVIEW")
    confidence: str = Field(default="LOW", description="HIGH | MEDIUM | LOW")
    discovery_path: List[str] = Field(default_factory=list, description="Audit trail of layers executed")
    last_error_code: str = Field(default="NONE")
    error_detail: str = Field(default="")
    resolved_by_layer: Optional[str] = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Phase1JobProgress(BaseModel):
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0


class Phase1JobRecord(BaseModel):
    """Async Phase 1 discovery job record stored in `phase1_jobs` collection."""
    job_id: str
    query_params: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="QUEUED", description="QUEUED | RUNNING | COMPLETED | FAILED")
    progress: Phase1JobProgress = Field(default_factory=Phase1JobProgress)
    scorecard: Dict[str, Any] = Field(default_factory=dict)
    results: List[UniversityDepartmentCache] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

