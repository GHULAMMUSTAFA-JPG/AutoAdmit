"""Admin routes for on-demand 3-Step Smart Diff-Sync and runtime AdminConfig guardrails."""

import hmac
from typing import Any
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.filters import AdminConfig

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])
logger = get_logger("api.routes_admin")


class ColabUrlUpdate(BaseModel):
    base_url: str


class AdminSyncRequest(BaseModel):
    domains: list[str]
    department: str = "Computer Science"
    degree: str = "masters"


class AdminConfigPatch(BaseModel):
    max_departments_per_request: int | None = None
    max_universities_per_job: int | None = None
    max_professors_per_uni: int | None = None
    max_concurrent_universities: int | None = None
    allowed_countries: list[str] | None = None
    enable_serper: bool | None = None
    enable_playwright: bool | None = None
    enable_agent_fallback: bool | None = None
    enable_colab_bridge: bool | None = None
    enable_llm_extraction: bool | None = None


@router.post("/sync")
async def trigger_admin_sync(body: AdminSyncRequest, request: Request):
    """Triggers 3-Step Smart Diff-Sync for selected university domains."""
    repo = request.app.state.repo
    diff_sync = request.app.state.diff_sync
    results: list[dict[str, Any]] = []

    for dom in body.domains:
        dept_doc = await repo.get_department_doc(dom, body.department, body.degree)
        if not dept_doc or not dept_doc.faculty_roster_url:
            results.append({"domain": dom, "ok": False, "detail": "No stored faculty_roster_url to sync."})
            continue
        res = await diff_sync.sync_roster(dom, body.department, dept_doc.faculty_roster_url)
        results.append({"domain": dom, "ok": res.ok, "data": res.data, "error_code": res.error_code})

    return {"synced": len(results), "results": results}


@router.get("/config", response_model=AdminConfig)
async def get_admin_config(request: Request):
    return request.app.state.admin_config


@router.patch("/config", response_model=AdminConfig)
async def patch_admin_config(patch: AdminConfigPatch, request: Request):
    cfg: AdminConfig = request.app.state.admin_config
    updates = patch.model_dump(exclude_none=True)
    new_cfg = cfg.model_copy(update=updates)
    request.app.state.admin_config = new_cfg
    # Propagate runtime guardrails & feature toggles to all active services
    for svc_name in ("phase1", "scraper", "extractor", "runner", "tree_builder"):
        svc = getattr(request.app.state, svc_name, None)
        if svc is not None and hasattr(svc, "admin"):
            svc.admin = new_cfg
    from app.core.llm_router import llm_router
    llm_router.enable_colab = new_cfg.enable_colab_bridge
    return new_cfg


@router.post("/colab-url")
async def update_colab_url(body: ColabUrlUpdate, request: Request):
    """Hot-swaps Tier 1 Colab Qwen URL in memory (zero restart, resets circuit-breaker) when Colab tunnel rotates."""
    provided = request.headers.get("X-API-Key", "")
    expected = settings.COLAB_API_KEY or ""
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key.")

    clean_url = body.base_url.strip().rstrip("/")
    if not clean_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="base_url must start with http:// or https://")

    from app.core.llm_router import llm_router
    from app.services.colab_client import colab_client

    llm_router.colab.base_url = f"{clean_url}/v1"
    llm_router._colab_open_until = 0.0
    colab_client.base_url = clean_url
    settings.COLAB_BASE_URL = clean_url

    logger.info("colab_url_synced", base_url=clean_url)
    return {"ok": True, "colab_base_url": clean_url, "circuit_reset": True}
