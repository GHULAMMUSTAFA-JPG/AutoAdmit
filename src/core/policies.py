"""Phase 1 Tool Policies, Admin Kill-Switches, Monthly Budget Caps, and Bounded Concurrency / Per-Domain Rate Limiters."""

import asyncio
import random
import time
from typing import Dict, Optional, Tuple

from src.config import settings
from src.core.telemetry import ErrorCode


class ToolPolicyManager:
    """Enforces admin kill-switches, monthly search API budget caps, and Playwright browser hygiene thresholds."""

    def __init__(self) -> None:
        self.enable_search_api: bool = settings.ENABLE_SEARCH_API
        self.enable_playwright: bool = settings.ENABLE_PLAYWRIGHT
        self.monthly_search_cap: int = settings.MONTHLY_SEARCH_CAP
        self.search_cost_per_call_usd: float = settings.SEARCH_COST_PER_CALL_USD
        self.search_calls_used: int = 0
        self.playwright_pages_rendered: int = 0
        self.max_playwright_pages_before_recycle: int = 50
        self._lock = asyncio.Lock()

    def check_search_allowed(self) -> Tuple[bool, ErrorCode]:
        """Checks whether L3 Search API can be invoked under current admin switches and budget cap."""
        if not self.enable_search_api:
            return False, ErrorCode.TOOL_DISABLED_BY_ADMIN
        if self.search_calls_used >= self.monthly_search_cap:
            return False, ErrorCode.BUDGET_CAP_EXCEEDED
        return True, ErrorCode.NONE

    async def reserve_search_call(self) -> Tuple[bool, ErrorCode, float]:
        """Atomically checks and increments the monthly search counter, returning (allowed, error_code, cost_usd)."""
        async with self._lock:
            allowed, code = self.check_search_allowed()
            if not allowed:
                return False, code, 0.0
            self.search_calls_used += 1
            return True, ErrorCode.NONE, self.search_cost_per_call_usd

    def check_playwright_allowed(self) -> Tuple[bool, ErrorCode]:
        """Checks whether L4 Playwright fallback is enabled by admin policy."""
        if not self.enable_playwright:
            return False, ErrorCode.TOOL_DISABLED_BY_ADMIN
        return True, ErrorCode.NONE

    async def record_playwright_page(self) -> bool:
        """Increments Playwright page counter and returns True if browser recycle threshold (every 50 pages) is hit."""
        async with self._lock:
            self.playwright_pages_rendered += 1
            return (self.playwright_pages_rendered % self.max_playwright_pages_before_recycle) == 0

    def update_policies(
        self,
        *,
        enable_search_api: Optional[bool] = None,
        enable_playwright: Optional[bool] = None,
        monthly_search_cap: Optional[int] = None,
        reset_search_counter: bool = False,
    ) -> Dict[str, object]:
        if enable_search_api is not None:
            self.enable_search_api = bool(enable_search_api)
            settings.ENABLE_SEARCH_API = self.enable_search_api
        if enable_playwright is not None:
            self.enable_playwright = bool(enable_playwright)
            settings.ENABLE_PLAYWRIGHT = self.enable_playwright
        if monthly_search_cap is not None and monthly_search_cap >= 0:
            self.monthly_search_cap = int(monthly_search_cap)
            settings.MONTHLY_SEARCH_CAP = self.monthly_search_cap
        if reset_search_counter:
            self.search_calls_used = 0
        return self.to_dict()

    def to_dict(self) -> Dict[str, object]:
        return {
            "enable_search_api": self.enable_search_api,
            "enable_playwright": self.enable_playwright,
            "monthly_search_cap": self.monthly_search_cap,
            "search_calls_used": self.search_calls_used,
            "search_calls_remaining": max(0, self.monthly_search_cap - self.search_calls_used),
            "search_cost_per_call_usd": self.search_cost_per_call_usd,
            "playwright_pages_rendered": self.playwright_pages_rendered,
            "max_playwright_pages_before_recycle": self.max_playwright_pages_before_recycle,
        }


class Phase1ConcurrencyController:
    """
    Bounded concurrency and per-domain rate limiter:
    - asyncio.Semaphore(5) for fast httpx probes
    - asyncio.Semaphore(1) for headless Playwright
    - Per-domain minimum delay (1.0s + random jitter) to prevent WAF triggers
    """

    def __init__(self) -> None:
        self._http_sem: Optional[asyncio.Semaphore] = None
        self._pw_sem: Optional[asyncio.Semaphore] = None
        self._domain_locks: Dict[str, asyncio.Lock] = {}
        self._domain_last_ts: Dict[str, float] = {}
        self.min_domain_delay: float = settings.PHASE1_DOMAIN_DELAY_SECONDS

    @property
    def http_semaphore(self) -> asyncio.Semaphore:
        if self._http_sem is None:
            self._http_sem = asyncio.Semaphore(max(1, settings.PHASE1_HTTP_CONCURRENCY))
        return self._http_sem

    @property
    def playwright_semaphore(self) -> asyncio.Semaphore:
        if self._pw_sem is None:
            self._pw_sem = asyncio.Semaphore(max(1, settings.PHASE1_PLAYWRIGHT_CONCURRENCY))
        return self._pw_sem

    async def wait_for_domain(self, domain: str) -> None:
        """Enforces >= min_domain_delay + random jitter between requests to the same registrable domain."""
        clean = (domain or "default").lower().strip()
        lock = self._domain_locks.setdefault(clean, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._domain_last_ts.get(clean, 0.0)
            if last > 0.0:
                jitter = random.uniform(0.05, 0.30)
                required_wait = (self.min_domain_delay + jitter) - (now - last)
                if required_wait > 0:
                    await asyncio.sleep(required_wait)
            self._domain_last_ts[clean] = time.monotonic()


policy_manager = ToolPolicyManager()
concurrency_controller = Phase1ConcurrencyController()
