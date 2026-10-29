"""University and Feasibility Scoring Pydantic schemas."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class FeasibilityTier(str, Enum):
    TIER_1_DREAM = "Tier 1 (Dream)"
    TIER_2_TARGET = "Tier 2 (Target)"
    TIER_3_SAFETY = "Tier 3 (Safety)"


class ScholarshipType(str, Enum):
    CSC_TYPE_B = "CSC Type B (Full Funding)"
    PROVINCIAL = "Provincial Government Scholarship"
    PRESIDENTIAL = "University Presidential Scholarship"
    BELT_AND_ROAD = "Silk Road / Belt and Road Grant"


class DepartmentEndpoint(BaseModel):
    name: str = Field(..., description="Department or School name (e.g., School of Computer Science)")
    url: str = Field(..., description="Official directory URL on .edu.cn domain")


class University(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., description="English Name of University")
    chinese_name: Optional[str] = Field(default=None, description="Native Chinese name")
    domain: str = Field(..., description="Official educational domain e.g. tsinghua.edu.cn")
    region: str = Field(default="National", description="Province or Municipal Region in China (e.g., Beijing, Shanghai, Jiangsu)")
    tier: FeasibilityTier = Field(..., description="Dream / Target / Safety tier")
    cs_ranking: Optional[int] = Field(default=None, description="National or global CS ranking")
    is_project_985: bool = Field(default=False)
    is_project_211: bool = Field(default=False)
    scholarships_available: List[ScholarshipType] = Field(default_factory=list)
    application_fee_rmb: int = Field(default=0, description="Application fee in RMB (0 if free)")
    feasibility_notes: str = Field(default="", description="GPA compensation notes and outreach focus")
    department_endpoints: List[DepartmentEndpoint] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreRunCostEstimate(BaseModel):
    total_target_departments: int
    estimated_pages_to_crawl: int
    estimated_faculty_count: int
    estimated_gemini_tokens: int
    estimated_runtime_seconds: int
    is_approved: bool = False
    approved_at: Optional[datetime] = None

