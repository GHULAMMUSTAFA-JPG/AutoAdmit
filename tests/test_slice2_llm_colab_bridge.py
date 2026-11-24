"""Slice 2 Tests: Multi-Key LLM Router failover & Colab GPU Bridge Client."""

import httpx
import pytest

from app.core.llm_router import LLMEndpoint, LLMRouter
from app.services.colab_client import ColabClient


@pytest.mark.asyncio
async def test_llm_router_primary_429_fails_over_to_backup():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "primary.test" in str(request.url):
            return httpx.Response(429, text="Rate limit exceeded")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        )

    router = LLMRouter(
        primary=LLMEndpoint("primary", "https://primary.test/v1", "key-1", "gemini-2.0-flash-lite", tier=2),
        backup=LLMEndpoint("backup", "https://backup.test/v1", "key-2", "gemini-3-8-flash", tier=3),
        enable_colab=False,
        backoff_delays=(0.0,),
    )
    res = await router.complete(
        [{"role": "user", "content": "hello"}],
        transport=httpx.MockTransport(handler),
    )
    assert res.ok is True
    assert res.data["provider"] == "backup"
    assert res.data["content"] == '{"status":"ok"}'
    assert len(calls) == 3  # 1 initial primary + 1 backoff retry + 1 backup


@pytest.mark.asyncio
async def test_colab_client_offline_and_timeout_graceful_fallback():
    # Unset URL -> fallback=True
    unset_client = ColabClient(base_url="", api_key="secret")
    res_unset = await unset_client.score_links("CS faculty", [{"text": "师资队伍", "href": "/faculty"}])
    assert res_unset.ok is False
    assert res_unset.data["fallback"] is True

    # Timeout -> fallback=True without raising
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    to_client = ColabClient(base_url="https://colab.test", api_key="secret")
    res_to = await to_client.html_to_markdown("<html>hi</html>", transport=httpx.MockTransport(timeout_handler))
    assert res_to.ok is False
    assert res_to.data["fallback"] is True


@pytest.mark.asyncio
async def test_colab_client_headers_and_mocked_responses():
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers[request.url.path] = dict(request.headers)
        if request.url.path == "/score-links":
            return httpx.Response(
                200,
                json={
                    "model": "bge-m3",
                    "results": [{"text": "师资队伍", "href": "https://cs.tsinghua.edu.cn/szdw", "score": 0.94}],
                    "latency_ms": 18,
                },
            )
        if request.url.path == "/html-to-md":
            return httpx.Response(
                200,
                json={"markdown": "# 张伟\n博士生导师", "latency_ms": 42},
            )
        return httpx.Response(404)

    client = ColabClient(base_url="https://colab.test", api_key="colab-secret-123")
    transport = httpx.MockTransport(handler)

    score_res = await client.score_links(
        "Computer Science masters supervisor",
        [{"text": "师资队伍", "href": "https://cs.tsinghua.edu.cn/szdw"}],
        model="bge-m3",
        top_k=3,
        transport=transport,
    )
    assert score_res.ok is True
    assert score_res.data["fallback"] is False
    assert score_res.data["results"][0]["score"] == 0.94
    assert captured_headers["/score-links"]["x-api-key"] == "colab-secret-123"

    md_res = await client.html_to_markdown("<h1>张伟</h1><p>博士生导师</p>", transport=transport)
    assert md_res.ok is True
    assert "张伟" in md_res.data["markdown"]
    assert captured_headers["/html-to-md"]["x-api-key"] == "colab-secret-123"


@pytest.mark.asyncio
async def test_llm_router_5xx_and_timeout_failover_and_both_fail():
    # Primary 503 -> Backup succeeds
    def h503(req: httpx.Request) -> httpx.Response:
        if "primary.test" in str(req.url):
            return httpx.Response(503, text="Service unavailable")
        return httpx.Response(200, json={"choices": [{"message": {"content": "backup-ok"}}]})

    router = LLMRouter(
        primary=LLMEndpoint("primary", "https://primary.test/v1", "k1", "m1", tier=2),
        backup=LLMEndpoint("backup", "https://backup.test/v1", "k2", "m2", tier=3),
        max_concurrency=2,
        enable_colab=False,
        backoff_delays=(0.0,),
    )
    r503 = await router.complete([{"role": "user", "content": "hi"}], transport=httpx.MockTransport(h503))
    assert r503.ok is True
    assert r503.data["provider"] == "backup"

    # Primary timeout -> Backup succeeds
    def h_to(req: httpx.Request) -> httpx.Response:
        if "primary.test" in str(req.url):
            raise httpx.ReadTimeout("primary slow")
        return httpx.Response(200, json={"choices": [{"message": {"content": "backup-after-timeout"}}]})

    r_to = await router.complete([{"role": "user", "content": "hi"}], transport=httpx.MockTransport(h_to))
    assert r_to.ok is True
    assert r_to.data["content"] == "backup-after-timeout"

    # Both fail -> typed StepResult(ok=False)
    def h_both_fail(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    r_fail = await router.complete([{"role": "user", "content": "hi"}], transport=httpx.MockTransport(h_both_fail))
    assert r_fail.ok is False
    assert r_fail.error_code == "LLM_RATE_LIMITED"
