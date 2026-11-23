"""Admin routes for on-demand 3-Step Smart Diff-Sync and runtime AdminConfig guardrails."""

from typing import Any
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.schemas.filters import AdminConfig

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


class AdminSyncRequest(BaseModel):
    domains: list[str]
    department: str = "Computer Science"
    degree: str = "masters"


class AdminConfigPatch(BaseModel):
    max_departments_per_request: int | None = None
    max_universities_per_job: int | None = None
    max_professors_per_uni: int | None = None
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
    for svc_name in ("phase1", "scraper", "extractor"):
        svc = getattr(request.app.state, svc_name, None)
        if svc is not None and hasattr(svc, "admin"):
            svc.admin = new_cfg
    return new_cfg
