"""Multi-Key OpenAI-compatible async LLM Router with automatic failover and bounded concurrency."""

import asyncio
from dataclasses import dataclass
from typing import Any
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult

logger = get_logger("core.llm_router")


@dataclass
class LLMEndpoint:
    """Single OpenAI-compatible chat completions provider configuration."""
    name: str
    base_url: str
    api_key: str
    model: str


class LLMRouter:
    """Routes async chat completions across Primary -> Backup endpoints with semaphore throttling."""

    def __init__(
        self,
        primary: LLMEndpoint | None = None,
        backup: LLMEndpoint | None = None,
        max_concurrency: int = 8,
        timeout_sec: float = 30.0,
    ) -> None:
        self.primary = primary or LLMEndpoint(
            name="primary",
            base_url=settings.PRIMARY_LLM_BASE_URL.rstrip("/"),
            api_key=settings.PRIMARY_LLM_API_KEY,
            model=settings.PRIMARY_LLM_MODEL,
        )
        self.backup = backup or LLMEndpoint(
            name="backup",
            base_url=settings.BACKUP_LLM_BASE_URL.rstrip("/"),
            api_key=settings.BACKUP_LLM_API_KEY,
            model=settings.BACKUP_LLM_MODEL,
        )
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self.timeout_sec = timeout_sec

    async def _post_completion(
        self,
        client: httpx.AsyncClient,
        ep: LLMEndpoint,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> tuple[bool, int, Any]:
        payload: dict[str, Any] = {
            "model": ep.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {ep.api_key}",
            "Content-Type": "application/json",
        }
        resp = await client.post(
            f"{ep.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_sec,
        )
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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> StepResult:
        """Executes chat completion on Primary; fails over to Backup on 429, 5xx, or timeout."""
        endpoints = [ep for ep in (self.primary, self.backup) if ep.base_url and ep.api_key]
        if not endpoints:
            return StepResult.fail(ErrorCode.LLM_ERROR, "No LLM API keys configured.")

        last_code = ErrorCode.LLM_ERROR
        last_detail = "All LLM endpoints failed."

        async with self._sem:
            async with httpx.AsyncClient(transport=transport) as client:
                for idx, ep in enumerate(endpoints):
                    try:
                        ok, status_code, payload = await self._post_completion(
                            client, ep, messages, temperature=temperature, json_mode=json_mode
                        )
                        if ok:
                            logger.info("llm_complete_ok", provider=ep.name, model=ep.model)
                            return StepResult.success({
                                "content": str(payload).strip(),
                                "provider": ep.name,
                                "model": ep.model,
                            })
                        if status_code == 429:
                            last_code = ErrorCode.LLM_RATE_LIMITED
                            last_detail = f"{ep.name} returned HTTP 429: {payload}"
                            logger.warning("llm_failover_429", provider=ep.name, next_available=idx + 1 < len(endpoints))
                            continue
                        if status_code >= 500:
                            last_code = ErrorCode.LLM_ERROR
                            last_detail = f"{ep.name} returned HTTP {status_code}: {payload}"
                            logger.warning("llm_failover_5xx", provider=ep.name, status_code=status_code)
                            continue
                        return StepResult.fail(
                            ErrorCode.LLM_ERROR,
                            f"{ep.name} returned HTTP {status_code}: {payload}",
                        )
                    except (httpx.TimeoutException, httpx.RequestError) as exc:
                        last_code = ErrorCode.HTTP_TIMEOUT
                        last_detail = f"{ep.name} network/timeout error: {exc}"
                        logger.warning("llm_failover_timeout", provider=ep.name, error=str(exc))
                        continue

        return StepResult.fail(last_code, last_detail)


llm_router = LLMRouter()
