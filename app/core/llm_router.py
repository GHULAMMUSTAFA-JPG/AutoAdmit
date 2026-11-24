"""3-Tier OpenAI-compatible async LLM Router:
Tier 1 (Colab 4-bit Qwen2.5-7B-Instruct, 30s timeout + 60s circuit-breaker)
-> Tier 2 (Primary API: Coarena DeepSeek, 2s->4s 429 backoff)
-> Tier 3 (Backup API: Google Gemini).
"""

import asyncio
from dataclasses import dataclass
import json
import time
import uuid
from typing import Any
import httpx

from app.core.config import settings
from app.core.logging import current_domain, current_job_id, get_logger
from app.core.types import ErrorCode, StepResult
from app.schemas.entities import ApiCallTraceDoc

logger = get_logger("core.llm_router")

COLAB_QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"


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
    """3-Tier async LLM router with Colab circuit-breaker, 429 exponential backoff, and structured latency logging."""

    def __init__(
        self,
        primary: LLMEndpoint | None = None,
        backup: LLMEndpoint | None = None,
        colab: LLMEndpoint | None = None,
        max_concurrency: int = 2,
        timeout_sec: float = 30.0,
        colab_timeout_sec: float = 30.0,
        colab_cooldown_sec: float = 60.0,
        backoff_delays: tuple[float, ...] = (2.0, 4.0),
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
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self.timeout_sec = timeout_sec
        self.colab_cooldown_sec = colab_cooldown_sec
        self.backoff_delays = backoff_delays
        self.enable_colab = enable_colab
        self._colab_open_until: float = 0.0
        self.trace_repo = trace_repo

    def set_trace_repo(self, repo: Any) -> None:
        """Attaches Repository instance for persisting per-attempt api_call_traces."""
        self.trace_repo = repo

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
                request_payload=(request_payload or "")[:8000],
                response_payload=(response_payload or "")[:8000],
            )
            await self.trace_repo.insert_api_call_trace(trace)
        except Exception as exc:
            logger.warning("api_trace_persist_failed", error=str(exc))

    def _is_colab_circuit_open(self) -> bool:
        return time.monotonic() < self._colab_open_until

    def _trip_colab_circuit(self, reason: str) -> None:
        self._colab_open_until = time.monotonic() + self.colab_cooldown_sec
        logger.warning("colab_circuit_opened", cooldown_sec=self.colab_cooldown_sec, reason=reason)

    async def _post_completion(
        self,
        client: httpx.AsyncClient,
        ep: LLMEndpoint,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[bool, int, Any]:
        payload: dict[str, Any] = {
            "model": ep.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

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
            return True, 200, content
        return False, resp.status_code, resp.text[:300]

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        json_mode: bool = False,
        max_tokens: int | None = None,
        use_colab: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        stage: str = "llm_complete",
    ) -> StepResult:
        """Routes completion through Tier 1 (Colab Qwen) -> Tier 2 (Primary + 429 backoff) -> Tier 3 (Backup comma-separated fallbacks)."""
        endpoints: list[LLMEndpoint] = []
        colab_allowed = self.enable_colab if use_colab is None else use_colab
        if colab_allowed and self.colab.base_url and self.colab.api_key:
            if self._is_colab_circuit_open():
                logger.info("colab_circuit_skip", tier=1, provider=self.colab.name)
            else:
                endpoints.append(self.colab)
        if self.primary.base_url and self.primary.api_key:
            endpoints.append(self.primary)
        if self.backup.base_url and self.backup.api_key:
            backup_models = [m.strip() for m in (self.backup.model or "").split(",") if m.strip()]
            for bm in backup_models:
                endpoints.append(
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

        if not endpoints:
            return StepResult.fail(ErrorCode.LLM_ERROR, "No LLM API keys configured.")

        req_preview = json.dumps(messages, ensure_ascii=False)[:8000]
        last_code = ErrorCode.LLM_ERROR
        last_detail = "All LLM endpoints failed."

        async with self._sem:
            async with httpx.AsyncClient(transport=transport) as client:
                for ep in endpoints:
                    # Tier 2 (Primary) retries 429 with exponential backoff (2s -> 4s) before failing over
                    max_attempts = (1 + len(self.backoff_delays)) if ep.tier == 2 else 1
                    for attempt in range(max_attempts):
                        t0 = time.perf_counter()
                        try:
                            ok, status_code, payload = await self._post_completion(
                                client, ep, messages,
                                temperature=temperature,
                                json_mode=json_mode,
                                max_tokens=max_tokens,
                            )
                            latency_ms = int((time.perf_counter() - t0) * 1000)
                            if ok:
                                content_str = str(payload).strip()
                                await self._record_trace(
                                    ep=ep,
                                    stage=stage,
                                    status="ok",
                                    http_status=200,
                                    error_detail="",
                                    latency_ms=latency_ms,
                                    request_payload=req_preview,
                                    response_payload=content_str,
                                )
                                logger.info(
                                    "llm_complete_ok",
                                    tier=ep.tier,
                                    provider=ep.name,
                                    model=ep.model,
                                    latency_ms=latency_ms,
                                )
                                return StepResult.success({
                                    "content": content_str,
                                    "tier": ep.tier,
                                    "provider": ep.name,
                                    "model": ep.model,
                                    "latency_ms": latency_ms,
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
                                if attempt < len(self.backoff_delays) and ep.tier == 2:
                                    delay = self.backoff_delays[attempt]
                                    if delay > 0:
                                        await asyncio.sleep(delay)
                                    continue
                                break  # Fail over to next tier/model

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
                            last_code = ErrorCode.HTTP_TIMEOUT
                            last_detail = f"Tier {ep.tier} ({ep.name}/{ep.model}) network/timeout error: {exc}"
                            await self._record_trace(
                                ep=ep,
                                stage=stage,
                                status="timeout" if is_timeout else "connection_error",
                                http_status=None,
                                error_detail=last_detail,
                                latency_ms=latency_ms,
                                request_payload=req_preview,
                                response_payload="",
                            )
                            logger.warning(
                                "llm_failover_timeout",
                                tier=ep.tier,
                                provider=ep.name,
                                model=ep.model,
                                latency_ms=latency_ms,
                                error=str(exc),
                            )
                            if ep.tier == 1:
                                self._trip_colab_circuit(str(exc))
                            break

        return StepResult.fail(last_code, last_detail)


llm_router = LLMRouter()
