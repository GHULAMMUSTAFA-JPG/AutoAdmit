"""Analytics endpoints for LLM/Serper latency, breakage tracking, and per-call request/response traces."""

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.db.repositories import Repository

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview(
    request: Request,
    job_id: str | None = Query(None),
):
    """Returns per-provider latency/health metrics and grouped failure_breakdown across colab_qwen, deepseek, gemini, serper."""
    repo: Repository = request.app.state.repo
    return await repo.get_api_analytics_overview(job_id=job_id)


@router.get("/traces")
async def analytics_traces(
    request: Request,
    job_id: str | None = Query(None),
    provider: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(60, ge=1, le=500),
):
    """Lists recent API/LLM call traces (compact view without full 8k payloads; fetch /traces/{trace_id} for full prompt/response)."""
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
