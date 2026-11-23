"""Optional HTTPS bridge to Google Colab GPU model server with graceful CPU fallback and full schema parity."""

from typing import Any, Literal
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult

logger = get_logger("services.colab_client")


class ColabClient:
    """Async client for Colab /health, /score-links (single & batch), and /html-to-md (single & batch)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_sec: float = 15.0,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.COLAB_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.COLAB_API_KEY
        self.timeout_sec = timeout_sec

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _fallback(self, reason: str) -> StepResult:
        logger.warning("colab_fallback", reason=reason)
        return StepResult.fail(
            ErrorCode.COLAB_UNAVAILABLE,
            reason,
            data={"fallback": True},
        )

    async def health(self, *, transport: httpx.AsyncBaseTransport | None = None) -> StepResult:
        """Checks Colab GPU server health, device name, VRAM, and loaded models."""
        if not self.base_url:
            return self._fallback("COLAB_BASE_URL is not configured.")
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers=self._headers(),
                    timeout=self.timeout_sec,
                )
            if resp.status_code != 200:
                return self._fallback(f"Colab /health returned HTTP {resp.status_code}")
            body = resp.json()
            body["fallback"] = False
            return StepResult.success(body)
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            return self._fallback(f"Colab /health unreachable: {exc}")

    async def score_links(
        self,
        query: str,
        links: list[dict[str, str]],
        *,
        model: Literal["minilm", "bge-m3"] = "minilm",
        top_k: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> StepResult:
        """Scores candidate anchor links against a query via Colab GPU embeddings."""
        if not self.base_url:
            return self._fallback("COLAB_BASE_URL is not configured.")
        payload: dict[str, Any] = {
            "query": query,
            "links": links,
            "model": model,
            "top_k": top_k,
        }
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    f"{self.base_url}/score-links",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_sec,
                )
            if resp.status_code != 200:
                return self._fallback(f"Colab /score-links returned HTTP {resp.status_code}")
            body = resp.json()
            body["fallback"] = False
            return StepResult.success(body)
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            return self._fallback(f"Colab /score-links unreachable: {exc}")

    async def score_links_batch(
        self,
        batch: list[dict[str, Any]],
        *,
        model: Literal["minilm", "bge-m3"] = "minilm",
        top_k: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> StepResult:
        """Scores multiple (query, links) items in one batched Colab GPU call."""
        if not self.base_url:
            return self._fallback("COLAB_BASE_URL is not configured.")
        payload: dict[str, Any] = {"batch": batch, "model": model, "top_k": top_k}
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    f"{self.base_url}/score-links",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_sec,
                )
            if resp.status_code != 200:
                return self._fallback(f"Colab /score-links (batch) returned HTTP {resp.status_code}")
            body = resp.json()
            body["fallback"] = False
            return StepResult.success(body)
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            return self._fallback(f"Colab /score-links (batch) unreachable: {exc}")

    async def html_to_markdown(
        self,
        html: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> StepResult:
        """Converts messy HTML to clean Markdown via Colab ReaderLM-v2."""
        if not self.base_url:
            return self._fallback("COLAB_BASE_URL is not configured.")
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    f"{self.base_url}/html-to-md",
                    headers=self._headers(),
                    json={"html": html},
                    timeout=self.timeout_sec,
                )
            if resp.status_code != 200:
                return self._fallback(f"Colab /html-to-md returned HTTP {resp.status_code}")
            body = resp.json()
            body["fallback"] = False
            return StepResult.success(body)
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            return self._fallback(f"Colab /html-to-md unreachable: {exc}")

    async def html_to_markdown_batch(
        self,
        htmls: list[str],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> StepResult:
        """Converts a batch of HTML pages to clean Markdown via Colab ReaderLM-v2."""
        if not self.base_url:
            return self._fallback("COLAB_BASE_URL is not configured.")
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    f"{self.base_url}/html-to-md",
                    headers=self._headers(),
                    json={"htmls": htmls},
                    timeout=self.timeout_sec,
                )
            if resp.status_code != 200:
                return self._fallback(f"Colab /html-to-md (batch) returned HTTP {resp.status_code}")
            body = resp.json()
            body["fallback"] = False
            return StepResult.success(body)
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            return self._fallback(f"Colab /html-to-md (batch) unreachable: {exc}")


colab_client = ColabClient()
