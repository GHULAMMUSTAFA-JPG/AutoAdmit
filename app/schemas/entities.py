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
    name_en: str = ""
    title: str = ""
    title_en: str = ""
    email: str = ""
    email_status: Literal["FOUND", "MISSING", "IMAGE_EMBEDDED"] = "MISSING"
    degree_eligibility: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    research_areas_en: list[str] = Field(default_factory=list)
    photo_url: str = ""
    name_evidence_quote: str = ""
    supervisor_evidence_quote: str = ""
    grounding_status: Literal["VERIFIED", "UNGROUNDED"] = "VERIFIED"
    status: Literal["ACTIVE", "POSSIBLY_INACTIVE"] = "ACTIVE"
    updated_at: datetime = Field(default_factory=utc_now)


class JobDoc(BaseModel):
    """Resumable async job checkpoint, per-university row details & scorecard document in `jobs`."""
    job_id: str
    request: dict[str, Any] = Field(default_factory=dict)
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"] = "QUEUED"
    target_domains: list[str] = Field(default_factory=list)
    completed_domains: list[str] = Field(default_factory=list)
    university_details: dict[str, dict[str, Any]] = Field(default_factory=dict)
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


class SiteTreeNode(BaseModel):
    """Single discovered node inside a university's pruned site tree."""
    url: str
    label: str
    zone: Literal["NAV", "SIDEBAR", "BODY"] = "BODY"
    depth: int = 0
    node_type: Literal["HOME", "SCHOOLS_DIR", "DEPT_HOME", "FACULTY_SECTION", "VERIFIED_ROSTER", "DEAD_END"] = "HOME"
    parent_url: str | None = None
    children: list[str] = Field(default_factory=list)


class VerifiedRosterEntry(BaseModel):
    """Cached verified faculty roster entry inside `university_site_trees.verified_rosters`."""
    roster_url: str
    department_url: str | None = None
    strategy: str = "TREE_DFS"
    candidate_profile_count: int = 0
    verified_at: datetime = Field(default_factory=utc_now)


class UniversitySiteTreeDoc(BaseModel):
    """Permanent pruned site hierarchy + department map + verified rosters in `university_site_trees`."""
    domain: str
    root_url: str
    nav_type: Literal["SEMANTIC_NAV", "DIV_BASED_NAV", "UNKNOWN"] = "UNKNOWN"
    markdown_tree: str = ""
    nodes: list[SiteTreeNode] = Field(default_factory=list)
    departments_map: dict[str, str] = Field(default_factory=dict)
    verified_rosters: dict[str, VerifiedRosterEntry] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class ApiCallTraceDoc(BaseModel):
    """Per-attempt LLM / Serper API latency and breakage trace in `api_call_traces`."""
    trace_id: str
    job_id: str = ""
    domain: str = ""
    stage: str = ""
    provider: str
    model: str = ""
    tier: int = 0
    status: str = "ok"
    http_status: int | None = None
    error_detail: str = ""
    latency_ms: int = 0
    request_payload: str = ""
    response_payload: str = ""
    created_at: datetime = Field(default_factory=utc_now)
