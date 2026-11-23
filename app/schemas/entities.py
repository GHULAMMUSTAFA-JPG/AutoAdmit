"""MongoDB document schemas for permanent storage (no TTL expiry)."""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UniversitySeed(BaseModel):
    """Curated university ranking seed document in `universities_seed`."""
    domain: str
    name: str
    chinese_name: str = ""
    country: str = "China"
    region: str
    rank: int = Field(..., ge=1)


class UniversityDeptDoc(BaseModel):
    """Resolved department & faculty roster record in `university_departments`."""
    domain: str
    department: str
    degree: Literal["masters", "phd", "both"]
    department_url: str | None = None
    faculty_roster_url: str | None = None
    parent_url: str | None = None
    winning_strategy: str = "NONE"
    navigation_path: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["COMPLETE", "NEEDS_REVIEW"] = "NEEDS_REVIEW"
    error_code: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class PageSnapshotDoc(BaseModel):
    """Permanent Clean Markdown snapshot in `page_snapshots` (strictly NO TTL)."""
    url: str
    domain: str
    markdown: str
    sha256: str
    breadcrumb: str = ""
    etag: str | None = None
    last_modified: str | None = None
    fetched_at: datetime = Field(default_factory=utc_now)


class ProfessorDoc(BaseModel):
    """Grounded professor record in `professors` keyed on canonical_profile_url."""
    canonical_profile_url: str
    university_domain: str
    department: str
    source_roster_url: str
    name: str
    title: str = ""
    email: str = ""
    email_status: Literal["FOUND", "MISSING", "IMAGE_EMBEDDED"] = "MISSING"
    degree_eligibility: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    name_evidence_quote: str = ""
    supervisor_evidence_quote: str = ""
    grounding_status: Literal["VERIFIED", "UNGROUNDED"] = "VERIFIED"
    status: Literal["ACTIVE", "POSSIBLY_INACTIVE"] = "ACTIVE"
    updated_at: datetime = Field(default_factory=utc_now)


class JobDoc(BaseModel):
    """Resumable async job checkpoint & scorecard document in `jobs`."""
    job_id: str
    request: dict[str, Any] = Field(default_factory=dict)
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"] = "QUEUED"
    target_domains: list[str] = Field(default_factory=list)
    completed_domains: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    scorecard: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class NeedsReviewDoc(BaseModel):
    """Failed or ungrounded item queued for manual review in `needs_review`."""
    domain: str
    url: str = ""
    stage: str
    error_code: str
    detail: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
