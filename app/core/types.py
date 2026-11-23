"""Typed pipeline result envelopes and explicit error taxonomy (zero silent failures)."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Explicit error codes emitted across Phase 1, Phase 2, and Diff-Sync pipelines."""
    NONE = "NONE"
    INVALID_REQUEST = "INVALID_REQUEST"
    ROBOTS_DISALLOWED = "ROBOTS_DISALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    HTTP_TIMEOUT = "HTTP_TIMEOUT"
    WAF_BLOCKED = "WAF_BLOCKED"
    NO_LINKS_FOUND = "NO_LINKS_FOUND"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_ERROR = "LLM_ERROR"
    COLAB_UNAVAILABLE = "COLAB_UNAVAILABLE"
    GROUNDING_FAILED = "GROUNDING_FAILED"
    NEGATED_SUPERVISOR = "NEGATED_SUPERVISOR"
    PLAYWRIGHT_ERROR = "PLAYWRIGHT_ERROR"
    AGENT_FAILED = "AGENT_FAILED"
    DB_ERROR = "DB_ERROR"


@dataclass
class StepResult:
    """Uniform return contract for every pipeline step to eliminate bare excepts."""
    ok: bool
    data: Any = None
    error_code: str | None = None
    detail: str | None = None

    @classmethod
    def success(cls, data: Any = None) -> "StepResult":
        return cls(ok=True, data=data, error_code=None, detail=None)

    @classmethod
    def fail(cls, error_code: ErrorCode | str, detail: str, data: Any = None) -> "StepResult":
        code = error_code.value if isinstance(error_code, ErrorCode) else str(error_code)
        return cls(ok=False, data=data, error_code=code, detail=detail)
