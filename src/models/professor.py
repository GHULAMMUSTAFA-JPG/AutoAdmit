"""Faculty profile and supervisor qualification Pydantic schemas."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


class SupervisorQualification(str, Enum):
    PHD_SUPERVISOR = "博士生导师"
    PHD_SUPERVISOR_SHORT = "博导"
    MASTERS_SUPERVISOR = "硕士生导师"
    MASTERS_SUPERVISOR_SHORT = "硕导"


class ExtractionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    UNVERIFIED = "UNVERIFIED"


class FacultyPublication(BaseModel):
    title: str
    year: Optional[int] = None
    venue: Optional[str] = None


class FacultyProfile(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., description="Romanized or English name")
    native_name: Optional[str] = Field(default=None, description="Native Chinese name (e.g., 张伟)")
    email: str = Field(..., description="De-obfuscated institutional email")
    university: str = Field(..., description="University name")
    department: str = Field(..., description="Department or School name")
    lab_name: Optional[str] = Field(default="", description="Research Center or Laboratory")
    qualification: SupervisorQualification = Field(..., description="Verified supervisory credential")
    is_supervisor: bool = Field(default=True, description="Strictly True for valid graduate supervisors")
    research_areas: List[str] = Field(default_factory=list, description="Primary research domains and keywords")
    recent_publications: List[FacultyPublication] = Field(default_factory=list, description="2-3 recent publication titles")
    source_url: str = Field(..., description="Direct official faculty profile URL")
    content_hash: str = Field(..., description="SHA-256 cryptographic hash of raw extracted HTML")
    worker_id: str = Field(..., description="Worker process ID for audit lineage")
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.VERIFIED)

