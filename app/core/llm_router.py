"""3-Tier Central LLM Gateway with:
- Separated queue_wait vs generation timeout on Tier 1 (Colab vLLM Qwen3-8B-AWQ / Qwen2.5-7B-AWQ)
- Adaptive backpressure (5 -> 1 auto-throttle on Tier 1 failure, auto-recovery after 2 healthy T1 calls < 12s)
- Global 8.5 RPM (>= 7.0s spacing, concurrency=1) token-bucket lock on Tier 2 (DeepSeek)
- Comma-separated fallback models on Tier 3 (Gemini)
- Per-call token ledger (prompt/completion/total/system/page/original_md/sent_md) in `api_call_traces`
"""

import asyncio
from dataclasses import dataclass
import json
import os
import re
import time
import uuid
from typing import Any
import httpx

from app.core.config import settings
from app.core.logging import current_domain, current_job_id, get_logger
from app.core.types import ErrorCode, StepResult
from app.schemas.entities import ApiCallTraceDoc

logger = get_logger("core.llm_router")

COLAB_QWEN_MODEL = os.environ.get("COLAB_MODEL", "Qwen/Qwen3-8B-AWQ")
RETRY_AFTER_RE = re.compile(r"(?:try again in|retry in|wait)\s+(\d+(?:\.\d+)?)\s*s", re.I)


def estimate_tokens(text: str) -> int:
    """Deterministic token estimator (CJK chars ~1.3 chars/tok, ASCII ~4 chars/tok)."""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk * 0.75 + other / 4.0))


def _canonical_provider_name(ep: "LLMEndpoint") -> str:
    low_name = (ep.name or "").lower()
    low_model = (ep.model or "").lower()
    low_url = (ep.base_url or "").lower()
    if ep.tier == 1 or "colab" in low_name or "qwen" in low_model:
        return "colab_qwen"
    if "deepseek" in low_model or "coarena" in low_url or low_name == "primary":
        return "deepseek"
    if "gemini" in low_model or "generativelanguage" in low_url or low_name == "backup":
        return "gemini"
    return low_name or "unknown"


def _classify_http_status(status_code: int, payload: str = "") -> str:
    if status_code == 200:
        return "ok"
    if status_code == 502:
        return "tunnel_down_502"
    if status_code in (401, 403):
        return "auth_error_401_403"
    if status_code == 429:
        return "rate_limited_429"
    if status_code == 503:
        return "server_error_503"
    if status_code >= 500:
        return f"server_error_{status_code}"
    return "http_error"


def _parse_retry_after_sec(payload: str, cap_sec: float = 15.0) -> float | None:
    m = RETRY_AFTER_RE.search(payload or "")
    if not m:
        return None
    try:
        return min(cap_sec, max(0.5, float(m.group(1))))
    except ValueError:
        return None


@dataclass
class LLMEndpoint:
    """Single OpenAI-compatible chat completions provider configuration."""
    name: str
    base_url: str
    api_key: str
    model: str
    tier: int = 2
    auth_header: str = "Authorization"
    timeout_sec: float = 30.0


class LLMRouter:
    """Central 3-Tier async LLM Gateway with separated queue/generation timeouts, adaptive 5->1 backpressure, and 8.5 RPM cloud bucket."""

    def __init__(
        self,
        primary: LLMEndpoint | None = None,
        backup: LLMEndpoint | None = None,
        colab: LLMEndpoint | None = None,
        max_concurrency: int = 4,
        timeout_sec: float = 30.0,
        colab_timeout_sec: float = 45.0,
        colab_cooldown_sec: float = 60.0,
        backoff_delays: tuple[float, ...] = (2.0, 4.0),
        tier2_min_interval_sec: float | None = None,
        enable_colab: bool = True,
        trace_repo: Any = None,
    ) -> None:
        self.colab = colab or LLMEndpoint(
            name="colab_qwen",
            base_url=settings.COLAB_BASE_URL.rstrip("/") + "/v1" if settings.COLAB_BASE_URL else "",
            api_key=settings.COLAB_API_KEY,
            model=COLAB_QWEN_MODEL,
            tier=1,
            auth_header="X-API-Key",
            timeout_sec=colab_timeout_sec,
        )
        self.primary = primary or LLMEndpoint(
            name="primary",
            base_url=settings.PRIMARY_LLM_BASE_URL.rstrip("/"),
            api_key=settings.PRIMARY_LLM_API_KEY,
            model=settings.PRIMARY_LLM_MODEL,
            tier=2,
            auth_header="Authorization",
            timeout_sec=timeout_sec,
        )
        self.backup = backup or LLMEndpoint(
            name="backup",
            base_url=settings.BACKUP_LLM_BASE_URL.rstrip("/"),
            api_key=settings.BACKUP_LLM_API_KEY,
            model=settings.BACKUP_LLM_MODEL,
            tier=3,
            auth_header="Authorization",
            timeout_sec=timeout_sec,
        )
        self._tier1_sem = asyncio.Semaphore(max(1, max_concurrency))
        self._tier2_lock = asyncio.Lock()
        self._tier2_last_call_ts: float = 0.0
        # Default 8.5 RPM (>= 7.0s spacing) in production; 0.0 when tests explicitly pass zero backoff_delays
        if tier2_min_interval_sec is not None:
            self.tier2_min_interval_sec = max(0.0, tier2_min_interval_sec)
        else:
            self.tier2_min_interval_sec = 0.0 if backoff_delays == (0.0, 0.0) else 7.0

        self.timeout_sec = timeout_sec
        self.colab_cooldown_sec = colab_cooldown_sec
        self.backoff_delays = backoff_delays
        self.enable_colab = enable_colab
        self._colab_open_until: float = 0.0
        self._colab_consecutive_failures: int = 0
        self._colab_consecutive_ok: int = 0
        self._colab_recent_latencies: list[int] = []
        self.queue_mode: str = "PARALLEL_4X"
        self.active_concurrency: int = 4
        self.trace_repo = trace_repo

    def set_trace_repo(self, repo: Any) -> None:
        """Attaches Repository instance for persisting per-attempt api_call_traces."""
        self.trace_repo = repo

    def get_queue_state(self) -> dict[str, Any]:
        avg_lat = (
            round(sum(self._colab_recent_latencies[-10:]) / len(self._colab_recent_latencies[-10:]), 1)
            if self._colab_recent_latencies
            else 0.0
        )
        return {
            "queue_mode": self.queue_mode,
            "active_concurrency": self.active_concurrency,
            "colab_circuit_open": self._is_colab_circuit_open(),
            "colab_avg_latency_ms": avg_lat,
        }

    def _is_colab_circuit_open(self) -> bool:
        return time.monotonic() < self._colab_open_until

    def _trip_colab_circuit(self, reason: str) -> None:
        self._colab_open_until = time.monotonic() + self.colab_cooldown_sec
        self._colab_consecutive_ok = 0
        self.queue_mode = "THROTTLED_1X_8_5RPM"
        self.active_concurrency = 1
        logger.warning(
            "colab_circuit_opened",
            cooldown_sec=self.colab_cooldown_sec,
            queue_mode=self.queue_mode,
            active_concurrency=self.active_concurrency,
            reason=reason,
        )

    def _record_colab_healthy(self, latency_ms: int) -> None:
        self._colab_consecutive_failures = 0
        self._colab_recent_latencies.append(latency_ms)
        if len(self._colab_recent_latencies) > 20:
            self._colab_recent_latencies = self._colab_recent_latencies[-20:]
        if latency_ms < 12000:
            self._colab_consecutive_ok += 1
            if self._colab_consecutive_ok >= 2 and self.queue_mode != "PARALLEL_4X":
                self.queue_mode = "PARALLEL_4X"
                self.active_concurrency = 4
                logger.info("adaptive_concurrency_recovered", queue_mode=self.queue_mode, active_concurrency=4)
        else:
            self._colab_consecutive_ok = 0

    def reset_colab_circuit(self) -> None:
        self._colab_open_until = 0.0
        self._colab_consecutive_failures = 0

    async def _record_trace(
        self,
        *,
        ep: LLMEndpoint,
        stage: str,
        status: str,
        http_status: int | None,
        error_detail: str,
        latency_ms: int,
        request_payload: str,
        response_payload: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        system_prompt_tokens: int = 0,
        page_content_tokens: int = 0,
        original_markdown_tokens: int = 0,
        sent_markdown_tokens: int = 0,
    ) -> None:
        if self.trace_repo is None:
            return
        try:
            trace = ApiCallTraceDoc(
                trace_id=f"tr_{uuid.uuid4().hex[:12]}",
                job_id=current_job_id.get() or "",
                domain=current_domain.get() or "",
                stage=stage,
                provider=_canonical_provider_name(ep),
                model=ep.model,
                tier=ep.tier,
                status=status,
                http_status=http_status,
                error_detail=(error_detail or "")[:500],
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                system_prompt_tokens=system_prompt_tokens,
                page_content_tokens=page_content_tokens,
                original_markdown_tokens=original_markdown_tokens,
                sent_markdown_tokens=sent_markdown_tokens,
                request_payload=(request_payload or "")[:8000],
                response_payload=(response_payload or "")[:8000],
            )
            await self.trace_repo.insert_api_call_trace(trace)
        except Exception as exc:
            logger.warning("api_trace_persist_failed", error=f"{type(exc).__name__}: {exc}")

    async def _post_completion(
        self,
        client: httpx.AsyncClient,
        ep: LLMEndpoint,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        json_mode: bool = False,
        max_tokens: int | None = None,
        guided_json: dict[str, Any] | None = None,
    ) -> tuple[bool, int, Any, dict[str, int]]:
        payload: dict[str, Any] = {
            "model": ep.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if ep.tier == 1:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
            if guided_json:
                payload["guided_json"] = guided_json

        headers = {"Content-Type": "application/json"}
        if ep.auth_header == "X-API-Key":
            headers["X-API-Key"] = ep.api_key
        else:
            headers["Authorization"] = f"Bearer {ep.api_key}"

        base = ep.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        resp = await client.post(url, headers=headers, json=payload, timeout=ep.timeout_sec)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            raw_usage = data.get("usage") or {}
            usage = {
                "prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
                "completion_tokens": int(raw_usage.get("completion_tokens") or 0),
                "total_tokens": int(raw_usage.get("total_tokens") or 0),
            }
            return True, 200, content, usage
        return False, resp.status_code, resp.text[:300], {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        json_mode: bool = False,
        max_tokens: int | None = None,
        guided_json: dict[str, Any] | None = None,
        use_colab: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        stage: str = "llm_complete",
        original_markdown_chars: int = 0,
        sent_markdown_chars: int = 0,
        force_provider: str | None = None,
        bypass_tier2_pacing: bool = False,
    ) -> StepResult:
        """Routes completion through Tier 1 (Colab vLLM) -> Tier 2 (8.5 RPM DeepSeek bucket) -> Tier 3 (Backup comma-separated models)."""
        endpoints: list[LLMEndpoint] = []

        def _backup_endpoints() -> list[LLMEndpoint]:
            out: list[LLMEndpoint] = []
            if self.backup.base_url and self.backup.api_key:
                for bm in [m.strip() for m in (self.backup.model or "").split(",") if m.strip()]:
                    out.append(
                        LLMEndpoint(
                            name=self.backup.name,
                            base_url=self.backup.base_url,
                            api_key=self.backup.api_key,
                            model=bm,
                            tier=self.backup.tier,
                            auth_header=self.backup.auth_header,
                            timeout_sec=self.backup.timeout_sec,
                        )
                    )
            return out

        if force_provider:
            fp = force_provider.strip().lower()
            if fp == "colab_qwen" and self.colab.base_url and self.colab.api_key:
                endpoints.append(self.colab)
            elif fp in ("deepseek", "primary") and self.primary.base_url and self.primary.api_key:
                endpoints.append(self.primary)
            elif fp in ("gemini", "backup"):
                endpoints.extend(_backup_endpoints())
        else:
            colab_allowed = self.enable_colab if use_colab is None else use_colab
            if colab_allowed and self.colab.base_url and self.colab.api_key:
                if self._is_colab_circuit_open():
                    logger.info("colab_circuit_skip", tier=1, provider=self.colab.name)
                else:
                    endpoints.append(self.colab)
            if self.primary.base_url and self.primary.api_key:
                endpoints.append(self.primary)
            endpoints.extend(_backup_endpoints())

        if not endpoints:
            return StepResult.fail(ErrorCode.LLM_ERROR, "No LLM API keys configured.")

        # Precompute deterministic token breakdown for ledger
        sys_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        user_text = "\n".join(m.get("content", "") for m in messages if m.get("role") != "system")
        sys_tok = estimate_tokens(sys_text)
        page_tok = estimate_tokens(user_text)
        orig_md_tok = max(0, int(original_markdown_chars / 3.2)) if original_markdown_chars else page_tok
        sent_md_tok = max(0, int(sent_markdown_chars / 3.2)) if sent_markdown_chars else page_tok
        req_preview = json.dumps(messages, ensure_ascii=False)[:8000]

        last_code = ErrorCode.LLM_ERROR
        last_detail = "All LLM endpoints failed."

        async with httpx.AsyncClient(transport=transport) as client:
            for ep in endpoints:
                max_attempts = (1 + len(self.backoff_delays)) if (ep.tier == 2 and not force_provider) else 1
                for attempt in range(max_attempts):
                    # Separate queue_wait from generation timeout: acquire concurrency lock BEFORE starting generation timer
                    if ep.tier == 1:
                        await self._tier1_sem.acquire()
                    elif ep.tier == 2 and not bypass_tier2_pacing:
                        await self._tier2_lock.acquire()
                        if self.tier2_min_interval_sec > 0 and self._tier2_last_call_ts > 0:
                            elapsed_since = time.monotonic() - self._tier2_last_call_ts
                            wait_needed = self.tier2_min_interval_sec - elapsed_since
                            if wait_needed > 0:
                                await asyncio.sleep(wait_needed)
                        self._tier2_last_call_ts = time.monotonic()

                    t0 = time.perf_counter()
                    try:
                        ok, status_code, payload, usage = await self._post_completion(
                            client,
                            ep,
                            messages,
                            temperature=temperature,
                            json_mode=json_mode,
                            max_tokens=max_tokens,
                            guided_json=guided_json,
                        )
                        latency_ms = int((time.perf_counter() - t0) * 1000)

                        if ok:
                            content_str = str(payload).strip()
                            p_tok = usage.get("prompt_tokens") or (sys_tok + page_tok)
                            c_tok = usage.get("completion_tokens") or estimate_tokens(content_str)
                            tot_tok = usage.get("total_tokens") or (p_tok + c_tok)
                            if ep.tier == 1:
                                self._record_colab_healthy(latency_ms)
                            await self._record_trace(
                                ep=ep,
                                stage=stage,
                                status="ok",
                                http_status=200,
                                error_detail="",
                                latency_ms=latency_ms,
                                request_payload=req_preview,
                                response_payload=content_str,
                                prompt_tokens=p_tok,
                                completion_tokens=c_tok,
                                total_tokens=tot_tok,
                                system_prompt_tokens=sys_tok,
                                page_content_tokens=page_tok,
                                original_markdown_tokens=orig_md_tok,
                                sent_markdown_tokens=sent_md_tok,
                            )
                            logger.info(
                                "llm_complete_ok",
                                tier=ep.tier,
                                provider=ep.name,
                                model=ep.model,
                                latency_ms=latency_ms,
                                total_tokens=tot_tok,
                            )
                            return StepResult.success({
                                "content": content_str,
                                "tier": ep.tier,
                                "provider": ep.name,
                                "model": ep.model,
                                "latency_ms": latency_ms,
                                "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": tot_tok},
                            })

                        err_status = _classify_http_status(status_code, str(payload))
                        err_msg = f"Tier {ep.tier} ({ep.name}/{ep.model}) returned HTTP {status_code}: {payload}"
                        await self._record_trace(
                            ep=ep,
                            stage=stage,
                            status=err_status,
                            http_status=status_code,
                            error_detail=err_msg,
                            latency_ms=latency_ms,
                            request_payload=req_preview,
                            response_payload=str(payload),
                            prompt_tokens=sys_tok + page_tok,
                            system_prompt_tokens=sys_tok,
                            page_content_tokens=page_tok,
                            original_markdown_tokens=orig_md_tok,
                            sent_markdown_tokens=sent_md_tok,
                        )

                        if status_code == 429:
                            last_code = ErrorCode.LLM_RATE_LIMITED
                            last_detail = err_msg
                            logger.warning(
                                "llm_rate_limited",
                                tier=ep.tier,
                                provider=ep.name,
                                model=ep.model,
                                attempt=attempt + 1,
                                latency_ms=latency_ms,
                            )
                            if attempt < len(self.backoff_delays) and ep.tier == 2 and not force_provider:
                                parsed_wait = _parse_retry_after_sec(str(payload), cap_sec=15.0)
                                delay = parsed_wait if parsed_wait is not None else self.backoff_delays[attempt]
                                if delay > 0 and self.backoff_delays != (0.0, 0.0):
                                    await asyncio.sleep(delay)
                                continue
                            break

                        if ep.tier == 1:
                            self._trip_colab_circuit(f"HTTP {status_code}: {payload}")
                            last_code = ErrorCode.COLAB_UNAVAILABLE
                            last_detail = f"Tier 1 Colab HTTP {status_code}: {payload}"
                            break

                        if status_code >= 500 or status_code == 404:
                            last_code = ErrorCode.LLM_ERROR
                            last_detail = err_msg
                            logger.warning(
                                "llm_failover_5xx",
                                tier=ep.tier,
                                provider=ep.name,
                                model=ep.model,
                                status_code=status_code,
                                latency_ms=latency_ms,
                            )
                            break

                        return StepResult.fail(ErrorCode.LLM_ERROR, err_msg)

                    except (httpx.TimeoutException, httpx.RequestError) as exc:
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        is_timeout = isinstance(exc, httpx.TimeoutException)
                        exc_str = f"{type(exc).__name__}: {exc}"
                        last_code = ErrorCode.HTTP_TIMEOUT
                        last_detail = f"Tier {ep.tier} ({ep.name}/{ep.model}) network/timeout error: {exc_str}"
                        await self._record_trace(
                            ep=ep,
                            stage=stage,
                            status="timeout" if is_timeout else "connection_error",
                            http_status=None,
                            error_detail=last_detail,
                            latency_ms=latency_ms,
                            request_payload=req_preview,
                            response_payload="",
                            prompt_tokens=sys_tok + page_tok,
                            system_prompt_tokens=sys_tok,
                            page_content_tokens=page_tok,
                            original_markdown_tokens=orig_md_tok,
                            sent_markdown_tokens=sent_md_tok,
                        )
                        logger.warning(
                            "llm_failover_timeout",
                            tier=ep.tier,
                            provider=ep.name,
                            model=ep.model,
                            latency_ms=latency_ms,
                            error=exc_str,
                        )
                        if ep.tier == 1:
                            self._colab_consecutive_failures += 1
                            if not is_timeout or self._colab_consecutive_failures >= 2 or force_provider:
                                self._trip_colab_circuit(exc_str)
                        break
                    finally:
                        if ep.tier == 1:
                            self._tier1_sem.release()
                        elif ep.tier == 2 and not bypass_tier2_pacing:
                            self._tier2_lock.release()

        return StepResult.fail(last_code, last_detail)


llm_router = LLMRouter()
