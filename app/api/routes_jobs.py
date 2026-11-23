"""FastAPI routes for job start (with instant DB fast-path), job status, and system summary."""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request, status

from app.db.repositories import Repository
from app.schemas.entities import JobDoc
from app.schemas.filters import AdminConfig, DiscoveryRequest, validate_discovery_request
from scripts.seed_universities import filter_university_seeds

router = APIRouter(prefix="/api/v1", tags=["Jobs"])


def _get_repo(request: Request) -> Repository:
    return request.app.state.repo


def _get_admin(request: Request) -> AdminConfig:
    return request.app.state.admin_config


@router.post("/jobs/start")
async def start_discovery_job(body: DiscoveryRequest, request: Request):
    """
    Validates filters against AdminConfig.
    If permanent MongoDB data already exists for all matched domains -> returns instant DB results ($0, <1s).
    Otherwise launches a background resumable job and returns job_id.
    """
    repo = _get_repo(request)
    admin = _get_admin(request)
    effective_limit = validate_discovery_request(body, admin)

    seeds = await filter_university_seeds(
        repo.db,
        country=body.country,
        regions=body.regions,
        tier=body.tier,
        limit=effective_limit,
    )
    domains = [s.domain for s in seeds]
    department = body.departments[0].strip()

    if not domains:
        return {"source": "database", "domains": [], "professors": [], "count": 0}

    # Instant DB check: if every target domain has a COMPLETE dept record & professors in MongoDB -> $0 instant return
    all_complete = True
    for dom in domains:
        doc = await repo.get_department_doc(dom, department, body.degree)
        if not doc or doc.status != "COMPLETE":
            all_complete = False
            break

    if all_complete:
        profs = await repo.list_professors(domains=domains, department=department)
        if profs:
            return {
                "source": "database",
                "domains": domains,
                "count": len(profs),
                "professors": [p.model_dump(mode="json") for p in profs],
            }

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job = JobDoc(
        job_id=job_id,
        request=body.model_dump(),
        status="QUEUED",
        target_domains=domains,
    )
    await repo.upsert_job(job)

    runner = request.app.state.runner
    asyncio.create_task(
        runner.run_job(
            domains=domains,
            department=department,
            degree=body.degree,
            job_id=job_id,
            request_meta=body.model_dump(),
        )
    )
    return {"source": "job", "job_id": job_id, "status": "QUEUED", "target_domains": domains}


@router.get("/jobs/{job_id}", response_model=JobDoc)
async def get_job_status(job_id: str, request: Request):
    repo = _get_repo(request)
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


@router.get("/system/summary")
async def get_system_summary(request: Request):
    """Fast indexed count_documents() summary."""
    repo = _get_repo(request)
    return await repo.get_system_summary()
