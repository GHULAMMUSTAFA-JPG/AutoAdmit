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
    queue_mode: str = "PARALLEL_4X"
    active_concurrency: int = 4
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
    grounding_audit: dict[str, Any] = Field(default_factory=dict)
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
    roster_mode: Literal["BIO_LINKS", "INLINE_TABLE"] = "BIO_LINKS"
    candidate_profile_count: int = 0
    verified_at: datetime = Field(default_factory=utc_now)


class UniversitySiteTreeDoc(BaseModel):
    """Permanent pruned site hierarchy + department map + verified rosters + navigation trail in `university_site_trees`."""
    domain: str
    root_url: str
    nav_type: Literal["SEMANTIC_NAV", "DIV_BASED_NAV", "UNKNOWN"] = "UNKNOWN"
    markdown_tree: str = ""
    nodes: list[SiteTreeNode] = Field(default_factory=list)
    departments_map: dict[str, str] = Field(default_factory=dict)
    verified_rosters: dict[str, VerifiedRosterEntry] = Field(default_factory=dict)
    navigation_trail: list[dict[str, Any]] = Field(default_factory=list)
    token_stats: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class ApiCallTraceDoc(BaseModel):
    """Per-attempt LLM / Serper API latency, token ledger, and breakage trace in `api_call_traces`."""
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
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    system_prompt_tokens: int = 0
    page_content_tokens: int = 0
    original_markdown_tokens: int = 0
    sent_markdown_tokens: int = 0
    request_payload: str = ""
    response_payload: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class BenchmarkRunDoc(BaseModel):
    """Stress-benchmark run summary persisted in `benchmark_runs`."""
    run_id: str
    provider: str
    model: str = ""
    concurrency: int = 1
    payload_size: str = "nav_500"
    batch_size: int = 5
    avg_input_tokens: float = 0.0
    avg_output_tokens: float = 0.0
    total_time_ms: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: int = 0
    requests_per_min: float = 0.0
    ok_count: int = 0
    fail_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class HttpFetchTraceDoc(BaseModel):
    """Per-fetch HTTP/Playwright diagnostic record in `http_fetch_traces`."""
    trace_id: str
    job_id: str = ""
    domain: str = ""
    stage: str = ""
    url: str
    engine: Literal["httpx", "playwright"] = "httpx"
    status_code: int | None = None
    error_detail: str = ""
    html_bytes: int = 0
    markdown_chars: int = 0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class Phase2LinkAuditDoc(BaseModel):
    """Per-roster Phase 2A link filtering breakdown in `phase2_link_audits`."""
    audit_id: str
    job_id: str = ""
    domain: str = ""
    roster_url: str
    total_links: int = 0
    kept_count: int = 0
    dropped_breakdown: dict[str, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class DomainPlaybookDoc(BaseModel):
    """Self-learning CMS & Domain Playbook persisted in `domain_playbooks`."""
    domain: str
    cms_fingerprint: str = "unknown"
    requires_playwright_waf_reload: bool = False
    verified_dept_url: str = ""
    verified_roster_urls: list[str] = Field(default_factory=list)
    roster_mode: Literal["BIO_LINKS", "INLINE_TABLE"] = "BIO_LINKS"
    last_failure_code: str = ""
    learned_notes: str = ""
    updated_at: datetime = Field(default_factory=utc_now)
