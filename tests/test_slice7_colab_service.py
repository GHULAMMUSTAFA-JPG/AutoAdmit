"""Slice 7 Tests: Standalone Colab T4 4-bit Qwen2.5-7B-Instruct OpenAI-compatible Server + E2E LLMRouter ASGI check."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.llm_router import COLAB_QWEN_MODEL, LLMEndpoint, LLMRouter
from colab_service.colab_server import QwenModelRegistry, create_colab_app


def _make_mocked_qwen_app(api_key: str = "super-secret-key"):
    reg = QwenModelRegistry()
    reg.device = "Tesla T4 (Mock)"
    reg.vram_allocated_mb = 5520.0
    reg.vram_total_mb = 15360.0
    reg.generate_fn = lambda msgs, temp, max_tok: '{"ok": true, "model": "qwen2.5-7b"}'
    return create_colab_app(registry=reg, api_key=api_key)


def test_colab_qwen_rejects_missing_invalid_and_unset_api_key():
    client = TestClient(_make_mocked_qwen_app())
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-API-Key": "wrong"}).status_code == 401

    # Fail closed when COLAB_API_KEY is empty
    closed_client = TestClient(_make_mocked_qwen_app(api_key=""))
    assert closed_client.get("/health", headers={"X-API-Key": ""}).status_code == 401
    assert closed_client.get("/health", headers={"X-API-Key": "any"}).status_code == 401


def test_colab_qwen_health_chat_completions_and_oom_limits():
    client = TestClient(_make_mocked_qwen_app())
    headers = {"X-API-Key": "super-secret-key"}

    rh = client.get("/health", headers=headers)
    assert rh.status_code == 200
    h = rh.json()
    assert h["gpu_device"] == "Tesla T4 (Mock)"
    assert h["model"] in ("Qwen/Qwen3-8B-AWQ", "Qwen/Qwen2.5-7B-Instruct-AWQ", "Qwen/Qwen2.5-7B-Instruct")
    assert h["vram_allocated_mb"] == 5520.0

    rc = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "messages": [{"role": "user", "content": "Extract JSON"}],
            "temperature": 0.0,
            "max_tokens": 128,
            "response_format": {"type": "json_object"},
        },
    )
    assert rc.status_code == 200
    body = rc.json()
    assert body["model"] in ("Qwen/Qwen3-8B-AWQ", "Qwen/Qwen2.5-7B-Instruct-AWQ", "Qwen/Qwen2.5-7B-Instruct")
    assert '"qwen2.5-7b"' in body["choices"][0]["message"]["content"]

    # OOM limit (>60,000 chars) returns 413
    r_big = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "x" * 60_005}]},
    )
    assert r_big.status_code == 413


@pytest.mark.asyncio
async def test_e2e_llm_router_tier1_directly_against_colab_qwen_asgi():
    colab_app = _make_mocked_qwen_app(api_key="colab-key-1")
    transport = httpx.ASGITransport(app=colab_app)

    router = LLMRouter(
        colab=LLMEndpoint("colab_qwen", "http://colab.local/v1", "colab-key-1", COLAB_QWEN_MODEL, tier=1, auth_header="X-API-Key", timeout_sec=30.0),
        primary=LLMEndpoint("primary", "", "", "", tier=2),
        backup=LLMEndpoint("backup", "", "", "", tier=3),
    )
    res = await router.complete([{"role": "user", "content": "hi"}], json_mode=True, transport=transport)
    assert res.ok is True
    assert res.data["tier"] == 1
    assert res.data["provider"] == "colab_qwen"
    assert '"qwen2.5-7b"' in res.data["content"]
