"""Analytics, Stress Benchmark Runner, and Live Colab GPU Status endpoints."""

import asyncio
import time
import uuid
from typing import Literal
import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm_router import llm_router
from app.core.logging import current_domain, current_job_id
from app.db.repositories import Repository
from app.schemas.entities import BenchmarkRunDoc

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

_BASE_CS_PROFILE_SNIPPET = (
    "## 张伟 (Wei Zhang)\n"
    "职称：教授、博士生导师、硕士生导师 | 计算机科学与技术学院\n"
    "邮箱：zhangwei [at] cs [dot] tsinghua [dot] edu [dot] cn\n"
    "研究方向：大模型推理优化、计算机视觉、分布式机器学习、自然语言处理。\n"
    "简介：长期从事人工智能与系统结构交叉研究，主持国家自然科学基金重点项目多项，招收计算机科学与技术专业博士及硕士研究生。\n"
)


def _build_benchmark_markdown(payload_size: str) -> str:
    if payload_size == "nav_500":
        return _BASE_CS_PROFILE_SNIPPET * 3
    if payload_size == "roster_2000":
        return _BASE_CS_PROFILE_SNIPPET * 12
    return _BASE_CS_PROFILE_SNIPPET * 28  # prof_4500 (~4,500 tokens / ~4,500+ chars)


class BenchmarkRequest(BaseModel):
    provider: Literal["colab_qwen", "deepseek", "gemini"] = Field(default="colab_qwen")
    concurrency: Literal[1, 2, 4, 6] = Field(default=2)
    payload_size: Literal["nav_500", "roster_2000", "prof_4500"] = Field(default="nav_500")
    batch_size: Literal[5, 10, 20] = Field(default=5)


@router.get("/overview")
async def analytics_overview(
    request: Request,
    job_id: str | None = Query(None),
):
    """Returns per-provider latency/token/health metrics, grouped failure_breakdown, and live queue_mode."""
    repo: Repository = request.app.state.repo
    ov = await repo.get_api_analytics_overview(job_id=job_id)
    ov["queue_state"] = llm_router.get_queue_state()
    return ov


@router.get("/traces")
async def analytics_traces(
    request: Request,
    job_id: str | None = Query(None),
    provider: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(60, ge=1, le=500),
):
    """Lists recent API/LLM call traces (compact view without full 8k payloads)."""
    repo: Repository = request.app.state.repo
    traces = await repo.list_api_call_traces(
        job_id=job_id,
        provider=provider,
        status=status_filter,
        limit=limit,
    )
    return [
        {
            "trace_id": t.trace_id,
            "job_id": t.job_id,
            "domain": t.domain,
            "stage": t.stage,
            "provider": t.provider,
            "model": t.model,
            "tier": t.tier,
            "status": t.status,
            "http_status": t.http_status,
            "error_detail": t.error_detail,
            "latency_ms": t.latency_ms,
            "prompt_tokens": t.prompt_tokens,
            "completion_tokens": t.completion_tokens,
            "total_tokens": t.total_tokens,
            "created_at": t.created_at.isoformat(),
        }
        for t in traces
    ]


@router.get("/traces/{trace_id}")
async def analytics_trace_detail(trace_id: str, request: Request):
    """Returns full sent request_payload and raw response_payload for a single API/LLM call trace."""
    repo: Repository = request.app.state.repo
    trace = await repo.get_api_call_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trace '{trace_id}' not found.")
    return trace.model_dump(mode="json")


@router.get("/colab-gpu")
async def colab_gpu_status():
    """Proxies live Colab /health for the Tab 4 Live GPU Status pill (VRAM, active_requests, engine, model)."""
    base = (settings.COLAB_BASE_URL or "").strip().rstrip("/")
    api_key = settings.COLAB_API_KEY or ""
    if not base:
        return {"status": "unconfigured", "loaded": False, "engine": "none", "vram_used_mb": 0, "vram_total_mb": 0, "active_requests": 0}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{base}/health", headers={"X-API-Key": api_key})
        if r.status_code == 200:
            data = r.json()
            data.setdefault("vram_used_mb", data.get("vram_allocated_mb", 0))
            data.setdefault("active_requests", 0)
            data.setdefault("engine", "vllm")
            return data
        return {"status": f"http_{r.status_code}", "loaded": False, "detail": r.text[:160], "vram_used_mb": 0, "vram_total_mb": 0, "active_requests": 0}
    except Exception as exc:
        return {"status": "offline", "loaded": False, "detail": f"{type(exc).__name__}: {exc}", "vram_used_mb": 0, "vram_total_mb": 0, "active_requests": 0}


@router.post("/benchmark")
async def run_llm_benchmark(body: BenchmarkRequest, request: Request):
    """Runs a controlled stress benchmark across provider/concurrency/payload_size/batch_size levers and persists summary."""
    repo: Repository = request.app.state.repo
    active_router = getattr(request.app.state, "benchmark_router", None) or llm_router
    run_id = f"bench_{uuid.uuid4().hex[:8]}"
    md_fixture = _build_benchmark_markdown(body.payload_size)
    sys_msg = (
        "Extract structured supervisor JSON verbatim from Markdown. "
        'Return ONLY JSON: {"name": str, "name_en": str, "title": str, "email": str, "degree_eligibility": [str]}.'
    )
    user_msg = f"Markdown:\n{md_fixture}"

    sem = asyncio.Semaphore(body.concurrency)
    latencies: list[int] = []
    in_tokens: list[int] = []
    out_tokens: list[int] = []
    ok_count = 0
    fail_count = 0
    model_used = ""

    job_tok = current_job_id.set(run_id)
    dom_tok = current_domain.set("benchmark.local")
    t_total_start = time.perf_counter()
    try:
        async def _one_call(idx: int) -> None:
            nonlocal ok_count, fail_count, model_used
            async with sem:
                t0 = time.perf_counter()
                res = await active_router.complete(
                    [{"role": "system", "content": sys_msg}, {"role": "user", "content": f"[Req #{idx}]\n{user_msg}"}],
                    json_mode=True,
                    max_tokens=180,
                    stage="benchmark",
                    original_markdown_chars=len(md_fixture),
                    sent_markdown_chars=len(md_fixture),
                    force_provider=body.provider,
                    bypass_tier2_pacing=True,
                )
                lat = int((time.perf_counter() - t0) * 1000)
                latencies.append(lat)
                if res.ok:
                    ok_count += 1
                    model_used = str(res.data.get("model") or model_used)
                    usage = res.data.get("usage") or {}
                    in_tokens.append(int(usage.get("prompt_tokens") or 0))
                    out_tokens.append(int(usage.get("completion_tokens") or 0))
                else:
                    fail_count += 1

        await asyncio.gather(*[_one_call(i + 1) for i in range(body.batch_size)])
    finally:
        current_domain.reset(dom_tok)
        current_job_id.reset(job_tok)

    total_time_ms = max(1, int((time.perf_counter() - t_total_start) * 1000))
    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0
    rpm = round((ok_count / (total_time_ms / 60000.0)), 1) if ok_count else 0.0

    doc = BenchmarkRunDoc(
        run_id=run_id,
        provider=body.provider,
        model=model_used or body.provider,
        concurrency=body.concurrency,
        payload_size=body.payload_size,
        batch_size=body.batch_size,
        avg_input_tokens=round(sum(in_tokens) / len(in_tokens), 1) if in_tokens else 0.0,
        avg_output_tokens=round(sum(out_tokens) / len(out_tokens), 1) if out_tokens else 0.0,
        total_time_ms=total_time_ms,
        avg_latency_ms=avg_lat,
        max_latency_ms=max_lat,
        requests_per_min=rpm,
        ok_count=ok_count,
        fail_count=fail_count,
    )
    await repo.insert_benchmark_run(doc)
    return doc.model_dump(mode="json")


@router.get("/benchmarks")
async def list_benchmarks(request: Request, limit: int = Query(30, ge=1, le=200)):
    """Returns saved stress-benchmark history sorted newest-first."""
    repo: Repository = request.app.state.repo
    runs = await repo.list_benchmark_runs(limit=limit)
    return [r.model_dump(mode="json") for r in runs]
