"""Slice 7 Tests: Standalone Colab GPU Model Server (X-API-Key auth, /health, /score-links, /html-to-md)."""

import pytest
from fastapi.testclient import TestClient

from colab_service.colab_server import ModelRegistry, create_colab_app


class _FakeEncoder:
    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            if "师资" in t or "supervisor" in t.lower():
                out.append([1.0, 0.0])
            else:
                out.append([0.0, 1.0])
        return out


def _make_mocked_app():
    reg = ModelRegistry()
    reg.device = "Tesla T4 (Mock)"
    reg.vram_used_mb = 5900.0
    reg.models["minilm"] = _FakeEncoder()
    reg.models["bge-m3"] = _FakeEncoder()
    reg.models["readerlm-v2"] = lambda html: "# 张伟\n博士生导师"
    return create_colab_app(registry=reg, api_key="super-secret-key")


def test_colab_server_rejects_missing_or_invalid_api_key():
    client = TestClient(_make_mocked_app())

    r_missing = client.get("/health")
    assert r_missing.status_code == 401

    r_wrong = client.get("/health", headers={"X-API-Key": "wrong-key"})
    assert r_wrong.status_code == 401


def test_colab_server_health_score_links_and_html_to_md():
    client = TestClient(_make_mocked_app())
    headers = {"X-API-Key": "super-secret-key"}

    # 1. /health
    rh = client.get("/health", headers=headers)
    assert rh.status_code == 200
    h = rh.json()
    assert h["gpu_device"] == "Tesla T4 (Mock)"
    assert set(h["loaded_models"]) == {"bge-m3", "minilm", "readerlm-v2"}

    # 2. /score-links (minilm & bge-m3)
    payload = {
        "query": "Computer Science supervisor 师资",
        "links": [
            {"text": "新闻动态", "href": "https://cs.u.edu.cn/news"},
            {"text": "师资队伍", "href": "https://cs.u.edu.cn/szdw"},
        ],
        "top_k": 2,
    }
    for mdl in ("minilm", "bge-m3"):
        rs = client.post("/score-links", headers=headers, json={**payload, "model": mdl})
        assert rs.status_code == 200
        d = rs.json()
        assert d["model"] == mdl
        assert d["results"][0]["href"] == "https://cs.u.edu.cn/szdw"
        assert d["results"][0]["score"] > d["results"][1]["score"]
        assert "latency_ms" in d

    # 3. /html-to-md
    rm = client.post("/html-to-md", headers=headers, json={"html": "<h1>张伟</h1><p>博士生导师</p>"})
    assert rm.status_code == 200
    md_body = rm.json()
    assert "张伟" in md_body["markdown"]
    assert "latency_ms" in md_body


def test_colab_server_fails_closed_when_api_key_unset_and_enforces_oom_limits():
    # Fail closed when COLAB_API_KEY is empty
    reg = ModelRegistry()
    reg.models["minilm"] = _FakeEncoder()
    reg.models["readerlm-v2"] = lambda html: "ok"
    app_closed = create_colab_app(registry=reg, api_key="")
    c_closed = TestClient(app_closed)
    assert c_closed.get("/health", headers={"X-API-Key": ""}).status_code == 401
    assert c_closed.get("/health", headers={"X-API-Key": "anything"}).status_code == 401

    # OOM protection: oversized HTML (>200k chars) and >200 links rejected with 413
    c_ok = TestClient(_make_mocked_app())
    headers = {"X-API-Key": "super-secret-key"}
    r_big_html = c_ok.post("/html-to-md", headers=headers, json={"html": "x" * 200_005})
    assert r_big_html.status_code == 413

    many_links = [{"text": f"L{i}", "href": f"https://u.edu.cn/{i}"} for i in range(205)]
    r_big_links = c_ok.post("/score-links", headers=headers, json={"query": "CS", "links": many_links, "model": "minilm"})
    assert r_big_links.status_code == 413


@pytest.mark.asyncio
async def test_e2e_colab_client_directly_against_colab_server_asgi():
    """End-to-end HTTP test connecting app/services/colab_client.py directly to colab_service/colab_server.py."""
    import httpx
    from app.services.colab_client import ColabClient

    colab_app = _make_mocked_app()
    transport = httpx.ASGITransport(app=colab_app)

    # 1. Wrong API key -> 401 -> ColabClient degrades cleanly with fallback=True
    bad_client = ColabClient(base_url="http://colab.local", api_key="wrong-key")
    bad_res = await bad_client.health(transport=transport)
    assert bad_res.ok is False
    assert bad_res.data["fallback"] is True

    # 2. Valid API key -> full schema parity across /health, /score-links (single+batch), /html-to-md (single+batch)
    good_client = ColabClient(base_url="http://colab.local", api_key="super-secret-key")

    h_res = await good_client.health(transport=transport)
    assert h_res.ok is True
    assert h_res.data["gpu_device"] == "Tesla T4 (Mock)"

    s_res = await good_client.score_links(
        "CS supervisor 师资",
        [
            {"text": "新闻", "href": "https://u.edu.cn/news"},
            {"text": "师资队伍", "href": "https://u.edu.cn/szdw"},
        ],
        model="bge-m3",
        top_k=2,
        transport=transport,
    )
    assert s_res.ok is True
    assert s_res.data["results"][0]["href"] == "https://u.edu.cn/szdw"

    sb_res = await good_client.score_links_batch(
        [{"query": "师资", "links": [{"text": "师资队伍", "href": "https://u.edu.cn/szdw"}]}],
        model="minilm",
        top_k=1,
        transport=transport,
    )
    assert sb_res.ok is True
    assert len(sb_res.data["batch_results"]) == 1

    m_res = await good_client.html_to_markdown("<h1>张伟</h1>", transport=transport)
    assert m_res.ok is True
    assert "张伟" in m_res.data["markdown"]

    mb_res = await good_client.html_to_markdown_batch(["<h1>A</h1>", "<h1>B</h1>"], transport=transport)
    assert mb_res.ok is True
    assert len(mb_res.data["markdowns"]) == 2
