"""Standalone Google Colab T4 GPU FastAPI Model Server (MiniLM, bge-m3, ReaderLM-v2) with X-API-Key auth."""

import gc
import hmac
import os
import time
from typing import Any, Literal
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# OOM protection limits for standard Colab T4 (15 GB VRAM / 12.7 GB System RAM)
MAX_LINKS_PER_REQ = 200
MAX_BATCH_SIZE = 16
MAX_HTML_CHARS = 200_000


class LinkItem(BaseModel):
    text: str
    href: str


class ScoreLinksRequest(BaseModel):
    query: str | None = None
    links: list[LinkItem] | None = None
    batch: list[dict[str, Any]] | None = None
    model: Literal["minilm", "bge-m3"] = "minilm"
    top_k: int = Field(default=3, ge=1, le=20)


class HtmlToMdRequest(BaseModel):
    html: str | None = None
    htmls: list[str] | None = None


class ModelRegistry:
    """Manages sequential GPU model loading (float16) to stay safely inside Colab T4 VRAM & RAM limits."""

    def __init__(self) -> None:
        self.models: dict[str, Any] = {}
        self.device: str = "cpu"
        self.vram_used_mb: float = 0.0

    def load_all_sequentially(self) -> None:
        """Loads MiniLM, bge-m3, and ReaderLM-v2 one-by-one onto CUDA float16 with gc + CUDA cache cleanup."""
        import torch
        from sentence_transformers import SentenceTransformer
        from transformers import AutoModelForCausalLM, AutoTokenizer

        use_cuda = torch.cuda.is_available()
        self.device = torch.cuda.get_device_name(0) if use_cuda else "cpu"
        target_dev = "cuda" if use_cuda else "cpu"
        dtype = torch.float16 if use_cuda else torch.float32
        st_kwargs = {"torch_dtype": dtype} if use_cuda else {}

        # 1. MiniLM (~0.5 GB VRAM in fp16)
        self.models["minilm"] = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            device=target_dev,
            model_kwargs=st_kwargs,
        )
        gc.collect()
        if use_cuda:
            torch.cuda.empty_cache()

        # 2. bge-m3 (~2.2 GB VRAM in fp16)
        self.models["bge-m3"] = SentenceTransformer(
            "BAAI/bge-m3",
            device=target_dev,
            model_kwargs=st_kwargs,
        )
        gc.collect()
        if use_cuda:
            torch.cuda.empty_cache()

        # 3. ReaderLM-v2 (~3.2 GB VRAM in fp16)
        tok = AutoTokenizer.from_pretrained("jinaai/ReaderLM-v2")
        mdl = AutoModelForCausalLM.from_pretrained("jinaai/ReaderLM-v2", torch_dtype=dtype).to(target_dev)
        mdl.eval()
        self.models["readerlm-v2"] = (tok, mdl)
        gc.collect()
        if use_cuda:
            torch.cuda.empty_cache()
            self.vram_used_mb = round(torch.cuda.memory_allocated() / (1024 * 1024), 1)

    def score_links(self, query: str, links: list[LinkItem], model_key: str, top_k: int) -> list[dict[str, Any]]:
        if len(links) > MAX_LINKS_PER_REQ:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Too many links ({len(links)}). Maximum allowed per request is {MAX_LINKS_PER_REQ}.",
            )
        encoder = self.models.get(model_key)
        if encoder is None:
            raise HTTPException(status_code=503, detail=f"Model '{model_key}' is not loaded.")
        texts = [f"{l.text} {l.href}" for l in links]
        if not texts:
            return []

        q_vec = encoder.encode([query], normalize_embeddings=True)[0]
        l_vecs = encoder.encode(texts, normalize_embeddings=True)
        scored = []
        for item, vec in zip(links, l_vecs):
            score = float(sum(float(a) * float(b) for a, b in zip(q_vec, vec)))
            scored.append({"text": item.text, "href": item.href, "score": round(score, 4)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def html_to_markdown(self, html: str) -> str:
        if len(html) > MAX_HTML_CHARS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"HTML payload too large ({len(html)} chars). Max allowed is {MAX_HTML_CHARS}.",
            )
        entry = self.models.get("readerlm-v2")
        if entry is None:
            raise HTTPException(status_code=503, detail="Model 'readerlm-v2' is not loaded.")
        if callable(entry):
            return str(entry(html))
        import torch
        tok, mdl = entry
        inputs = tok(html[:12000], return_tensors="pt").to(mdl.device)
        with torch.no_grad():
            out = mdl.generate(**inputs, max_new_tokens=2048, do_sample=False)
        decoded = tok.decode(out[0], skip_special_tokens=True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return decoded


def create_colab_app(registry: ModelRegistry | None = None, api_key: str | None = None) -> FastAPI:
    reg = registry or ModelRegistry()
    # Explicitly preserve "" when passed so tests can verify fail-closed behavior
    fixed_key = api_key

    app = FastAPI(title="AutoAdmit Colab GPU Model Server", version="1.0.0")
    app.state.registry = reg

    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        provided = request.headers.get("X-API-Key", "")
        expected = fixed_key if fixed_key is not None else os.environ.get("COLAB_API_KEY", "")
        # Fail closed if COLAB_API_KEY is unset or empty
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing or invalid X-API-Key header."},
            )
        return await call_next(request)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "gpu_device": reg.device,
            "vram_used_mb": reg.vram_used_mb,
            "loaded_models": sorted(reg.models.keys()),
        }

    @app.post("/score-links")
    def score_links_endpoint(body: ScoreLinksRequest):
        t0 = time.perf_counter()
        if body.batch is not None:
            if len(body.batch) > MAX_BATCH_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Batch too large ({len(body.batch)}). Max allowed is {MAX_BATCH_SIZE}.",
                )
            batch_results = []
            for item in body.batch:
                q = str(item.get("query") or "")
                lks = [LinkItem(**x) for x in (item.get("links") or [])]
                batch_results.append(reg.score_links(q, lks, body.model, body.top_k))
            return {
                "model": body.model,
                "batch_results": batch_results,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            }

        if not body.query or body.links is None:
            raise HTTPException(status_code=400, detail="Provide either (query + links) or batch.")
        results = reg.score_links(body.query, body.links, body.model, body.top_k)
        return {
            "model": body.model,
            "results": results,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    @app.post("/html-to-md")
    def html_to_md_endpoint(body: HtmlToMdRequest):
        t0 = time.perf_counter()
        if body.htmls is not None:
            if len(body.htmls) > MAX_BATCH_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Batch too large ({len(body.htmls)}). Max allowed is {MAX_BATCH_SIZE}.",
                )
            mds = [reg.html_to_markdown(h) for h in body.htmls]
            return {
                "markdowns": mds,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            }
        if body.html is None:
            raise HTTPException(status_code=400, detail="Provide either html or htmls.")
        md = reg.html_to_markdown(body.html)
        return {
            "markdown": md,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    return app


app = create_colab_app()
