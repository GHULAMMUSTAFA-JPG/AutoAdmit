"""Phase 1 Observability Engine: Typed Error Taxonomy, StepResult, Structured JSONL Logger, and Self-Measuring Run Scorecard."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, TypeVar

from src.config import settings
from src.core.logger import setup_logger

try:
    import structlog  # type: ignore
    _HAS_STRUCTLOG = True
except ImportError:
    structlog = None  # type: ignore
    _HAS_STRUCTLOG = False

T = TypeVar("T")


class ErrorCode(str, Enum):
    """Explicit typed error taxonomy for Phase 1 discovery and fallback transitions."""
    NONE = "NONE"
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    SSL_ERROR = "SSL_ERROR"
    HTTP_4XX_NOT_FOUND = "HTTP_4XX_NOT_FOUND"
    HTTP_5XX_SERVER_ERROR = "HTTP_5XX_SERVER_ERROR"
    WAF_CHALLENGE_BLOCKED = "WAF_CHALLENGE_BLOCKED"        # 403/412/521 or JS anti-bot splash
    ROBOTS_TXT_DISALLOWED = "ROBOTS_TXT_DISALLOWED"
    ENCODING_DECODE_FAILED = "ENCODING_DECODE_FAILED"
    DEPT_LINK_NOT_FOUND = "DEPT_LINK_NOT_FOUND"
    FACULTY_ROSTER_NOT_FOUND = "FACULTY_ROSTER_NOT_FOUND"
    FALSE_POSITIVE_PAGE = "FALSE_POSITIVE_PAGE"            # Login/SSO/News/Undergrad page
    BUDGET_CAP_EXCEEDED = "BUDGET_CAP_EXCEEDED"
    TOOL_DISABLED_BY_ADMIN = "TOOL_DISABLED_BY_ADMIN"
    UNHANDLED_INTERNAL_ERROR = "UNHANDLED_INTERNAL_ERROR"


class TerminalStatus(str, Enum):
    """Honest terminal states for every (university, discipline) resolution."""
    COMPLETE = "COMPLETE"          # Homepage + Department URL + Faculty Roster URL verified
    PARTIAL = "PARTIAL"            # Homepage + Department URL verified, Faculty Roster URL missing
    NOT_FOUND = "NOT_FOUND"        # Homepage & Search ran cleanly, discipline does not exist
    NEEDS_REVIEW = "NEEDS_REVIEW"  # WAF block, persistent timeout, robots.txt, or budget cap


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class StepResult(Generic[T]):
    """Typed return contract for every discovery layer; eliminates silent except-pass failures."""
    ok: bool
    value: Optional[T] = None
    error_code: ErrorCode = ErrorCode.NONE
    error_detail: str = ""
    layer: str = ""
    http_status: Optional[int] = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    attempt: int = 1


class Phase1StructuredLogger:
    """Emits machine-readable JSONL records to logs/phase1.jsonl, stdout, and WebSocket stream."""

    def __init__(self) -> None:
        Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
        self.jsonl_path = Path(settings.LOG_DIR) / "phase1.jsonl"
        self._ws_logger = setup_logger("Phase1Telemetry")
        self._file_logger = logging.getLogger("Phase1JSONL")
        self._file_logger.setLevel(logging.INFO)
        self._file_logger.propagate = False

        if not self._file_logger.handlers:
            handler = RotatingFileHandler(
                self.jsonl_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._file_logger.addHandler(handler)

        if _HAS_STRUCTLOG and structlog is not None:
            structlog.configure(
                processors=[
                    structlog.processors.JSONRenderer(ensure_ascii=False)
                ],
                wrapper_class=structlog.BoundLogger,
                context_class=dict,
                logger_factory=structlog.ReturnLoggerFactory(),
                cache_logger_on_first_use=False,
            )
            self._struct_logger = structlog.get_logger()
        else:
            self._struct_logger = None

    def emit(
        self,
        *,
        trace_id: str,
        university_domain: str,
        discipline: str,
        layer: str,
        action: str,
        level: str = "INFO",
        stage: str = "DEPT_DISCOVERY",
        next_layer: Optional[str] = None,
        http_status: Optional[int] = None,
        latency_ms: int = 0,
        error_code: ErrorCode = ErrorCode.NONE,
        error_detail: str = "",
        cost_usd: float = 0.0,
        attempt: int = 1,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Formats and writes one structured telemetry event."""
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level.upper(),
            "trace_id": trace_id,
            "phase": "PHASE_1",
            "stage": stage,
            "university_domain": university_domain,
            "discipline": discipline,
            "layer": layer,
            "action": action,
            "next_layer": next_layer,
            "http_status": http_status,
            "latency_ms": int(latency_ms),
            "error_code": error_code.value if isinstance(error_code, ErrorCode) else str(error_code),
            "error_detail": error_detail,
            "cost_usd": round(float(cost_usd), 6),
            "attempt": attempt,
        }
        if extra:
            payload.update(extra)

        if self._struct_logger is not None:
            json_line = self._struct_logger.msg(**payload)
        else:
            json_line = json.dumps(payload, ensure_ascii=False)

        self._file_logger.info(json_line)
        summary = (
            f"[{trace_id}] [{university_domain}] [{discipline}] {layer} -> {action}"
            + (f" (next: {next_layer})" if next_layer else "")
            + (f" [{payload['error_code']}: {error_detail}]" if payload["error_code"] != "NONE" else "")
            + f" ({latency_ms}ms)"
        )
        if level.upper() in ("ERROR", "CRITICAL"):
            self._ws_logger.error(summary)
        elif level.upper() == "WARNING":
            self._ws_logger.warning(summary)
        else:
            self._ws_logger.info(summary)
        return payload


@dataclass
class JobScorecard:
    """Self-Measuring Run Scorecard tracking funnel conversion, layer efficiency, latency percentiles, and cost economics."""
    job_id: str
    target_universities: int = 0
    cache_hits: int = 0
    fresh_attempted: int = 0
    homepage_reachable: int = 0
    department_resolved: int = 0
    faculty_roster_verified: int = 0

    terminal_counts: Dict[str, int] = field(default_factory=lambda: {
        TerminalStatus.COMPLETE.value: 0,
        TerminalStatus.PARTIAL.value: 0,
        TerminalStatus.NOT_FOUND.value: 0,
        TerminalStatus.NEEDS_REVIEW.value: 0,
    })
    layer_resolution_counts: Dict[str, int] = field(default_factory=lambda: {
        "CACHE": 0,
        "L2_HTTP_NAV": 0,
        "L3_SEARCH_API": 0,
        "L4_PLAYWRIGHT": 0,
    })
    error_breakdown: Dict[str, int] = field(default_factory=dict)
    latencies_ms: List[int] = field(default_factory=list)
    search_api_calls: int = 0
    estimated_cost_usd: float = 0.0
    started_at_monotonic: float = 0.0
    total_duration_sec: float = 0.0

    def record_outcome(
        self,
        *,
        status: TerminalStatus,
        resolved_by_layer: Optional[str],
        latency_ms: int,
        homepage_ok: bool,
        dept_ok: bool,
        roster_ok: bool,
        from_cache: bool = False,
        error_code: ErrorCode = ErrorCode.NONE,
        search_calls: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        if from_cache:
            self.cache_hits += 1
        else:
            self.fresh_attempted += 1

        if homepage_ok:
            self.homepage_reachable += 1
        if dept_ok:
            self.department_resolved += 1
        if roster_ok:
            self.faculty_roster_verified += 1

        st_key = status.value if isinstance(status, TerminalStatus) else str(status)
        self.terminal_counts[st_key] = self.terminal_counts.get(st_key, 0) + 1

        if resolved_by_layer and resolved_by_layer in self.layer_resolution_counts:
            self.layer_resolution_counts[resolved_by_layer] += 1

        err_key = error_code.value if isinstance(error_code, ErrorCode) else str(error_code)
        if err_key and err_key != ErrorCode.NONE.value:
            self.error_breakdown[err_key] = self.error_breakdown.get(err_key, 0) + 1

        if latency_ms >= 0:
            self.latencies_ms.append(int(latency_ms))

        self.search_api_calls += int(search_calls)
        self.estimated_cost_usd += float(cost_usd)

    @staticmethod
    def _percentile(sorted_vals: List[int], pct: float) -> int:
        if not sorted_vals:
            return 0
        idx = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
        idx = max(0, min(idx, len(sorted_vals) - 1))
        return int(sorted_vals[idx])

    def _compute_health_grade(self, usable_pct: float) -> str:
        pct_int = int(round(usable_pct))
        if usable_pct >= 90.0:
            letter = "A"
        elif usable_pct >= 80.0:
            letter = "B+"
        elif usable_pct >= 70.0:
            letter = "B"
        elif usable_pct >= 55.0:
            letter = "C"
        else:
            letter = "D"
        return f"{letter} ({pct_int}% Usable Coverage)"

    def to_dict(self) -> Dict[str, Any]:
        total = max(1, self.target_universities or (self.cache_hits + self.fresh_attempted))
        usable = (
            self.terminal_counts.get(TerminalStatus.COMPLETE.value, 0)
            + self.terminal_counts.get(TerminalStatus.PARTIAL.value, 0)
        )
        usable_pct = (usable / total) * 100.0 if (self.cache_hits + self.fresh_attempted) > 0 else 0.0

        resolved_total = max(1, sum(self.layer_resolution_counts.values()))
        sorted_lat = sorted(self.latencies_ms)
        p50 = self._percentile(sorted_lat, 50.0)
        p95 = self._percentile(sorted_lat, 95.0)

        verified_unis = max(1, usable) if usable > 0 else 1
        cost_per_verified = round(self.estimated_cost_usd / verified_unis, 5) if usable > 0 else 0.0

        return {
            "job_id": self.job_id,
            "target_universities": self.target_universities,
            "health_grade": self._compute_health_grade(usable_pct),
            "funnel": {
                "1_cache_hits": self.cache_hits,
                "2_fresh_attempted": self.fresh_attempted,
                "3_homepage_reachable": self.homepage_reachable,
                "4_department_resolved": self.department_resolved,
                "5_faculty_roster_verified": self.faculty_roster_verified,
            },
            "terminal_statuses": dict(self.terminal_counts),
            "layer_efficiency": {
                "resolved_by_cache": f"{(self.layer_resolution_counts['CACHE'] / resolved_total) * 100.0:.1f}%",
                "resolved_by_L2_http_nav": f"{(self.layer_resolution_counts['L2_HTTP_NAV'] / resolved_total) * 100.0:.1f}%",
                "resolved_by_L3_search_api": f"{(self.layer_resolution_counts['L3_SEARCH_API'] / resolved_total) * 100.0:.1f}%",
                "resolved_by_L4_playwright": f"{(self.layer_resolution_counts['L4_PLAYWRIGHT'] / resolved_total) * 100.0:.1f}%",
            },
            "error_breakdown": dict(self.error_breakdown),
            "performance": {
                "total_duration_sec": round(self.total_duration_sec, 2),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
            },
            "cost_economics": {
                "search_api_calls": self.search_api_calls,
                "estimated_cost_usd": round(self.estimated_cost_usd, 4),
                "cost_per_verified_university_usd": cost_per_verified,
            },
        }


phase1_logger = Phase1StructuredLogger()
