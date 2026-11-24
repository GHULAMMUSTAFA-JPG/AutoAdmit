"""FastAPI routes for job start, job status, un-truncated per-run logs, professors, needs-review, and summary."""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.core.logging import get_job_log_path, read_job_logs
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, NeedsReviewDoc, ProfessorDoc
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
        return {"source": "database", "domains": [], "professors": [], "university_details": {}, "count": 0}

    # Instant DB check: if every target domain has a COMPLETE dept record & professors in MongoDB -> $0 instant return
    all_complete = True
    dept_docs = {}
    for dom in domains:
        doc = await repo.get_department_doc(dom, department, body.degree)
        if not doc or doc.status != "COMPLETE":
            all_complete = False
            break
        dept_docs[dom] = doc

    if all_complete:
        profs = await repo.list_professors(domains=domains, department=department)
        if profs:
            uni_details = {}
            for s in seeds:
                d_doc = dept_docs[s.domain]
                d_profs = [p for p in profs if p.university_domain == s.domain]
                uni_details[s.domain] = {
                    "domain": s.domain,
                    "name": s.name,
                    "chinese_name": s.chinese_name,
                    "region": s.region,
                    "rank": s.rank,
                    "winning_strategy": d_doc.winning_strategy,
                    "faculty_roster_url": d_doc.faculty_roster_url,
                    "department_url": d_doc.department_url,
                    "professors_found": len(d_profs),
                    "professors_verified": len(d_profs),
                    "status": "COMPLETE",
                    "error_code": None,
                    "detail": "Served from permanent MongoDB ($0)",
                }
            return {
                "source": "database",
                "domains": domains,
                "count": len(profs),
                "university_details": uni_details,
                "professors": [p.model_dump(mode="json") for p in profs],
            }

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    uni_details_init = {
        s.domain: {
            "domain": s.domain,
            "name": s.name,
            "chinese_name": s.chinese_name,
            "region": s.region,
            "rank": s.rank,
            "winning_strategy": "PENDING",
            "faculty_roster_url": None,
            "department_url": None,
            "professors_found": 0,
            "professors_verified": 0,
            "status": "QUEUED",
            "error_code": None,
            "detail": "",
        }
        for s in seeds
    }
    job = JobDoc(
        job_id=job_id,
        request=body.model_dump(),
        status="QUEUED",
        target_domains=domains,
        university_details=uni_details_init,
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
    return {
        "source": "job",
        "job_id": job_id,
        "status": "QUEUED",
        "target_domains": domains,
        "university_details": uni_details_init,
    }


@router.get("/jobs/{job_id}", response_model=JobDoc)
async def get_job_status(job_id: str, request: Request):
    repo = _get_repo(request)
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    level: str | None = Query(None),
    domain: str | None = Query(None),
):
    """Returns paginated, un-truncated JSONL log entries for a job run."""
    try:
        return read_job_logs(job_id, offset=offset, limit=limit, level=level, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/jobs/{job_id}/logs/download")
async def download_job_logs(job_id: str):
    """Downloads the full raw logs/jobs/{job_id}.jsonl file without truncation."""
    try:
        path = get_job_log_path(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return FileResponse(path=str(path), filename=f"{job_id}.jsonl", media_type="application/x-ndjson")


@router.get("/universities")
async def list_universities_overview(request: Request):
    """Returns seeded universities enriched with latest Phase 1 dept status and verified professor counts."""
    repo = _get_repo(request)
    seeds = await repo.query_university_seeds(limit=500)
    depts = await repo.list_department_docs()
    profs = await repo.list_professors()

    dept_by_dom = {}
    for d in depts:
        prev = dept_by_dom.get(d.domain)
        if not prev or d.status == "COMPLETE":
            dept_by_dom[d.domain] = d

    prof_counts: dict[str, int] = {}
    for p in profs:
        prof_counts[p.university_domain] = prof_counts.get(p.university_domain, 0) + 1

    rows = []
    for s in seeds:
        d = dept_by_dom.get(s.domain)
        rows.append({
            "domain": s.domain,
            "name": s.name,
            "chinese_name": s.chinese_name,
            "region": s.region,
            "rank": s.rank,
            "winning_strategy": d.winning_strategy if d else "PENDING",
            "faculty_roster_url": d.faculty_roster_url if d else None,
            "department_url": d.department_url if d else None,
            "professors_found": prof_counts.get(s.domain, 0),
            "professors_verified": prof_counts.get(s.domain, 0),
            "status": d.status if d else "PENDING",
            "error_code": d.error_code if d else None,
            "detail": "",
        })
    return rows


@router.get("/professors", response_model=list[ProfessorDoc])
async def list_professors_endpoint(
    request: Request,
    domain: str | None = Query(None),
    department: str | None = Query(None),
    email_status: str | None = Query(None),
    search: str | None = Query(None),
):
    """Lists verified professors from permanent MongoDB storage with optional filters."""
    repo = _get_repo(request)
    domains = [domain.lower().strip()] if domain else None
    profs = await repo.list_professors(domains=domains, department=department)
    if email_status:
        profs = [p for p in profs if p.email_status == email_status]
    if search:
        q = search.strip().lower()
        profs = [
            p for p in profs
            if q in p.name.lower()
            or q in p.university_domain.lower()
            or any(q in ri.lower() for ri in p.research_interests)
        ]
    return profs


@router.get("/needs-review", response_model=list[NeedsReviewDoc])
async def list_needs_review_endpoint(
    request: Request,
    domain: str | None = Query(None),
    stage: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """Lists failed, robots-disallowed, or ungrounded items from `needs_review`."""
    repo = _get_repo(request)
    return await repo.list_needs_review(domain=domain, stage=stage, limit=limit)


@router.get("/system/summary")
async def get_system_summary(request: Request):
    """Fast indexed count_documents() summary."""
    repo = _get_repo(request)
    return await repo.get_system_summary()
