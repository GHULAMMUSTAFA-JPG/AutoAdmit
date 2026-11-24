"""Structured JSON logging with un-truncated per-run job JSONL file sink + console output."""

from contextvars import ContextVar
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any
import structlog

_CONFIGURED = False
JOBS_LOG_DIR = Path("logs/jobs")

current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)
current_domain: ContextVar[str | None] = ContextVar("current_domain", default=None)

_SAFE_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def get_job_log_path(job_id: str, base_dir: Path | None = None) -> Path:
    """Returns safe path logs/jobs/{job_id}.jsonl (prevents path traversal)."""
    clean = (job_id or "").strip()
    if not clean or not _SAFE_JOB_ID_RE.match(clean):
        raise ValueError(f"Invalid job_id for log path: {job_id!r}")
    root = base_dir or JOBS_LOG_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{clean}.jsonl"


def _attach_context_and_write_jsonl(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor: injects active job_id/domain and appends every line to logs/jobs/{job_id}.jsonl."""
    jid = event_dict.get("job_id") or current_job_id.get()
    dom = event_dict.get("domain") or current_domain.get()
    if jid:
        event_dict["job_id"] = jid
    if dom:
        event_dict["domain"] = dom

    if jid and _SAFE_JOB_ID_RE.match(str(jid)):
        try:
            path = get_job_log_path(str(jid))
            line = json.dumps(event_dict, ensure_ascii=False, default=str)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # Never crash pipeline execution due to disk write failure
            pass
    return event_dict


def read_job_logs(
    job_id: str,
    *,
    offset: int = 0,
    limit: int = 500,
    level: str | None = None,
    domain: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Reads un-truncated JSONL log entries with offset/limit pagination and optional level/domain filters."""
    path = get_job_log_path(job_id, base_dir=base_dir)
    if not path.exists():
        return {"total": 0, "offset": offset, "next_offset": offset, "entries": []}

    matched: list[dict[str, Any]] = []
    lvl_filter = level.strip().lower() if level else None
    dom_filter = domain.strip().lower() if domain else None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except ValueError:
                continue
            if lvl_filter and str(entry.get("level", "")).lower() != lvl_filter:
                continue
            if dom_filter and dom_filter not in str(entry.get("domain", "")).lower():
                continue
            matched.append(entry)

    total = len(matched)
    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 5000))
    page = matched[safe_offset : safe_offset + safe_limit]
    next_offset = safe_offset + len(page)
    return {
        "total": total,
        "offset": safe_offset,
        "next_offset": next_offset,
        "entries": page,
    }


def configure_logging(level: int = logging.INFO) -> None:
    """Configures structlog once for console JSON output + per-job JSONL file sink."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _attach_context_and_write_jsonl,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str):
    """Returns a bound structlog JSON logger for the given module."""
    configure_logging()
    return structlog.get_logger(module=name)
