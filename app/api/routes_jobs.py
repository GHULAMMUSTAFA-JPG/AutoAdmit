"""FastAPI routes for job start, job status, un-truncated per-run logs, professors, needs-review, and summary."""

import asyncio
import csv
import io
import json
import uuid
import zipfile
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response

from app.core.job_control import freeze_run_archive, register_job_task, request_job_stop
from app.core.logging import get_job_log_path, read_job_logs
from app.db.repositories import Repository
from app.schemas.entities import JobDoc, NeedsReviewDoc, ProfessorDoc, utc_now
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
    task = asyncio.create_task(
        runner.run_job(
            domains=domains,
            department=department,
            degree=body.degree,
            job_id=job_id,
            request_meta=body.model_dump(),
        )
    )
    register_job_task(job_id, task)
    return {
        "source": "job",
        "job_id": job_id,
        "status": "QUEUED",
        "target_domains": domains,
        "university_details": uni_details_init,
    }


@router.get("/jobs/active")
async def get_active_running_job(request: Request):
    """Returns the currently RUNNING or QUEUED job (if any) so hard browser refreshes seamlessly re-attach."""
    repo = _get_repo(request)
    job = await repo.get_active_job()
    if not job:
        return {"active": False, "job": None}
    return {"active": True, "job": job.model_dump(mode="json")}


@router.get("/jobs/history")
async def get_jobs_history(request: Request, limit: int = Query(30, ge=1, le=100)):
    """Returns recent job runs with frozen archive status so every past run's full logs ZIP can be downloaded."""
    repo = _get_repo(request)
    jobs = await repo.list_recent_jobs(limit=limit)
    out = []
    for j in jobs:
        arch = await repo.get_run_archive(j.job_id)
        req = j.request or {}
        regs = req.get("regions") or []
        reg_str = ", ".join(regs) if isinstance(regs, list) and regs else "All Regions"
        mode_str = str((j.scorecard or {}).get("mode") or ("TREE_ONLY" if j.job_id.startswith("tree_") else ("TREE_EXTRACT" if j.job_id.startswith("ext_") else "FULL_PIPELINE")))
        out.append({
            "job_id": j.job_id,
            "status": j.status,
            "mode": mode_str,
            "region": reg_str,
            "done": len(j.completed_domains or []),
            "total": len(j.target_domains or []),
            "verified_professors": int((j.scorecard or {}).get("total_verified_professors") or (j.scorecard or {}).get("rosters_verified") or 0),
            "has_frozen_archive": arch is not None,
            "started_at": j.started_at.isoformat() if j.started_at else "",
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })
    return out


@router.post("/jobs/{job_id}/stop")
async def stop_running_job(job_id: str, request: Request):
    """Cooperatively stops a RUNNING or QUEUED pipeline job, checkpoints progress, and freezes its run archive."""
    repo = _get_repo(request)
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    cancelled_task = request_job_stop(job_id)
    if job.status in ("RUNNING", "QUEUED"):
        job.status = "STOPPED"
        job.completed_at = utc_now()
        await repo.upsert_job(job)
        await freeze_run_archive(repo, job_id)
    return {"job_id": job_id, "status": job.status, "task_cancelled": cancelled_task}


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
    """Returns seeded universities enriched with site tree nav_type, mapped depts, Phase 1 status, and verified professor counts."""
    repo = _get_repo(request)
    seeds = await repo.query_university_seeds(limit=2000)
    depts = await repo.list_department_docs()
    profs = await repo.list_professors()
    trees = await repo.list_site_trees(limit=2000)

    dept_by_dom = {}
    for d in depts:
        prev = dept_by_dom.get(d.domain)
        if not prev or d.status == "COMPLETE":
            dept_by_dom[d.domain] = d

    tree_by_dom = {t.domain: t for t in trees}

    prof_counts: dict[str, int] = {}
    for p in profs:
        prof_counts[p.university_domain] = prof_counts.get(p.university_domain, 0) + 1

    rows = []
    for s in seeds:
        d = dept_by_dom.get(s.domain)
        t = tree_by_dom.get(s.domain)
        roster_url = d.faculty_roster_url if d else None
        if not roster_url and t and t.verified_rosters:
            first_vr = next(iter(t.verified_rosters.values()))
            roster_url = first_vr.roster_url
        rows.append({
            "domain": s.domain,
            "name": s.name,
            "chinese_name": s.chinese_name,
            "region": s.region,
            "rank": s.rank,
            "nav_type": t.nav_type if t else "UNKNOWN",
            "departments_mapped_count": len(t.departments_map) if t else 0,
            "verified_rosters_count": len(t.verified_rosters) if t else 0,
            "token_stats": t.token_stats if t else {},
            "winning_strategy": d.winning_strategy if d else "PENDING",
            "faculty_roster_url": roster_url,
            "department_url": d.department_url if d else None,
            "professors_found": prof_counts.get(s.domain, 0),
            "professors_verified": prof_counts.get(s.domain, 0),
            "status": d.status if d else ("COMPLETE" if (t and t.verified_rosters) else "PENDING"),
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
            or q in (p.name_en or "").lower()
            or q in (p.title_en or "").lower()
            or q in p.university_domain.lower()
            or any(q in ri.lower() for ri in p.research_interests)
            or any(q in ra.lower() for ra in p.research_areas_en)
        ]
    return profs


@router.get("/needs-review", response_model=list[NeedsReviewDoc])
async def list_needs_review_endpoint(
    request: Request,
    domain: str | None = Query(None),
    stage: str | None = Query(None),
    error_code: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """Lists failed, robots-disallowed, or ungrounded items from `needs_review`."""
    repo = _get_repo(request)
    items = await repo.list_needs_review(domain=domain, stage=stage, limit=limit)
    if error_code:
        ec = error_code.strip()
        items = [it for it in items if it.error_code == ec]
    return items


@router.get("/export/universities")
async def export_universities_data(
    request: Request,
    fmt: str = Query("csv", alias="format"),
    region: str | None = Query(None),
    worked_only: bool = Query(True),
):
    """Downloads region-scoped worked universities with ALL details (trees, tokens, nav trails, rosters, prof counts) as CSV or JSON."""
    repo = _get_repo(request)
    rows = await list_universities_overview(request)
    trees_by_dom = {t.domain: t for t in await repo.list_site_trees(limit=2000)}

    reg_clean = (region or "").strip().lower()
    filtered: list[dict] = []
    for r in rows:
        if reg_clean and (r.get("region") or "").strip().lower() != reg_clean:
            continue
        worked = (
            r.get("status") != "PENDING"
            or (r.get("departments_mapped_count") or 0) > 0
            or (r.get("verified_rosters_count") or 0) > 0
            or (r.get("professors_verified") or 0) > 0
            or bool(r.get("faculty_roster_url"))
        )
        if worked_only and not worked:
            continue
        t = trees_by_dom.get(r["domain"])
        ts = r.get("token_stats") or {}
        enriched = {
            **r,
            "total_tokens": ts.get("total_tokens", 0),
            "qwen_tokens": ts.get("qwen_tokens", 0),
            "deepseek_tokens": ts.get("deepseek_tokens", 0),
            "gemini_tokens": ts.get("gemini_tokens", 0),
            "elapsed_sec": ts.get("elapsed_sec", 0),
        }
        if fmt.lower() == "json" and t is not None:
            enriched["navigation_trail"] = t.navigation_trail
            enriched["verified_rosters"] = {k: v.model_dump(mode="json") for k, v in t.verified_rosters.items()}
            enriched["departments_map"] = t.departments_map
        filtered.append(enriched)

    suffix = f"_{reg_clean.replace(' ', '_')}" if reg_clean else "_worked"
    if fmt.lower() == "json":
        content = json.dumps(filtered, ensure_ascii=False, indent=2)
        return Response(
            content=content.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="autoadmit_universities{suffix}.json"'},
        )
    buf = io.StringIO()
    fields = [
        "rank", "domain", "name", "chinese_name", "region", "nav_type", "status",
        "winning_strategy", "department_url", "faculty_roster_url", "departments_mapped_count",
        "verified_rosters_count", "professors_verified", "total_tokens", "qwen_tokens",
        "deepseek_tokens", "gemini_tokens", "elapsed_sec", "error_code",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in filtered:
        writer.writerow(r)
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="autoadmit_universities{suffix}.csv"'},
    )


@router.get("/export/professors")
async def export_professors_data(
    request: Request,
    domain: str | None = Query(None),
    region: str | None = Query(None),
    fmt: str = Query("csv", alias="format"),
):
    """Downloads verified professors (optionally scoped by `domain` or `region`) as CSV or JSON."""
    repo = _get_repo(request)
    clean_dom = domain.lower().strip() if domain else None
    reg_clean = (region or "").strip().lower()
    domains_filter: list[str] | None = [clean_dom] if clean_dom else None
    if not domains_filter and reg_clean:
        seeds = await repo.query_university_seeds(limit=2000)
        domains_filter = [s.domain for s in seeds if (s.region or "").strip().lower() == reg_clean]
    profs = await repo.list_professors(domains=domains_filter) if (domains_filter is None or len(domains_filter) > 0) else []
    safe_suffix = clean_dom.replace(".", "_") if clean_dom else (reg_clean.replace(" ", "_") if reg_clean else "all")

    if fmt.lower() == "json":
        payload = [p.model_dump(mode="json") for p in profs]
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            content=content.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="professors_{safe_suffix}.json"'},
        )

    buf = io.StringIO()
    fields = [
        "university_domain", "department", "name_en", "name", "title_en", "title",
        "email", "email_status", "degree_eligibility", "research_areas_en",
        "research_interests", "canonical_profile_url", "photo_url",
        "supervisor_evidence_quote", "status",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for p in profs:
        d = p.model_dump(mode="json")
        d["degree_eligibility"] = "; ".join(d.get("degree_eligibility") or [])
        d["research_areas_en"] = "; ".join(d.get("research_areas_en") or [])
        d["research_interests"] = "; ".join(d.get("research_interests") or [])
        writer.writerow(d)
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="professors_{safe_suffix}.csv"'},
    )


@router.get("/export/debug-bundle")
async def export_debug_bundle(
    request: Request,
    job_id: str | None = Query(None),
):
    """Exports a comprehensive JSON Debug Bundle containing job metadata, API traces, HTTP fetch traces, link audits, navigation trails, professors, and needs_review grounding audits."""
    repo = _get_repo(request)
    job_doc = await repo.get_job(job_id) if job_id else None
    api_traces = await repo.list_api_call_traces(job_id=job_id, limit=500)
    http_traces = await repo.list_http_fetch_traces(job_id=job_id, limit=500)
    link_audits = await repo.list_phase2_link_audits(job_id=job_id, limit=200)
    trees = await repo.list_site_trees(limit=500)
    profs = await repo.list_professors()
    reviews = await repo.list_needs_review(limit=500)

    bundle = {
        "job_id": job_id,
        "job": job_doc.model_dump(mode="json") if job_doc else None,
        "api_call_traces": [t.model_dump(mode="json") for t in api_traces],
        "http_fetch_traces": [t.model_dump(mode="json") for t in http_traces],
        "phase2_link_audits": [a.model_dump(mode="json") for a in link_audits],
        "university_site_trees": [
            {
                "domain": t.domain,
                "nav_type": t.nav_type,
                "departments_mapped_count": len(t.departments_map),
                "verified_rosters": {k: v.model_dump(mode="json") for k, v in t.verified_rosters.items()},
                "navigation_trail": t.navigation_trail,
                "token_stats": t.token_stats,
            }
            for t in trees
        ],
        "professors": [p.model_dump(mode="json") for p in profs],
        "needs_review": [r.model_dump(mode="json") for r in reviews],
    }
    safe_name = f"debug_bundle_{job_id}.json" if job_id else "debug_bundle_latest.json"
    content = json.dumps(bundle, ensure_ascii=False, indent=2)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.get("/export/run-logs-zip")
async def export_run_logs_zip(
    request: Request,
    job_id: str | None = Query(None),
):
    """Packages EVERY log & diagnostic trace for a single run into one downloadable .zip archive."""
    repo = _get_repo(request)
    jid = (job_id or "").strip()
    if not jid:
        latest = await repo.db["jobs"].find_one({}, sort=[("created_at", -1)])
        jid = str(latest["job_id"]) if latest and latest.get("job_id") else ""
    if not jid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No job_id found to export.")

    job_doc = await repo.get_job(jid)
    frozen = await repo.get_run_archive(jid)
    if frozen and frozen.snapshot_payload:
        sp = frozen.snapshot_payload
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("job_summary.json", json.dumps(sp.get("job_summary") or {"job_id": jid}, ensure_ascii=False, indent=2))
            zf.writestr(f"{jid}.jsonl", (sp.get("jsonl_text") or "").encode("utf-8"))
            zf.writestr("api_call_traces.json", json.dumps(sp.get("api_call_traces") or [], ensure_ascii=False, indent=2))
            zf.writestr("http_fetch_traces.json", json.dumps(sp.get("http_fetch_traces") or [], ensure_ascii=False, indent=2))
            zf.writestr("phase2_link_audits.json", json.dumps(sp.get("phase2_link_audits") or [], ensure_ascii=False, indent=2))
            zf.writestr("site_trees.json", json.dumps(sp.get("site_trees") or [], ensure_ascii=False, indent=2))
            zf.writestr("domain_playbooks.json", json.dumps(sp.get("domain_playbooks") or [], ensure_ascii=False, indent=2))
            zf.writestr("professors.json", json.dumps(sp.get("professors") or [], ensure_ascii=False, indent=2))
            zf.writestr("needs_review.json", json.dumps(sp.get("needs_review") or [], ensure_ascii=False, indent=2))
        return Response(
            content=zbuf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="run_{jid}_all_logs.zip"'},
        )

    target_domains = set(job_doc.target_domains) if job_doc else set()

    api_traces = await repo.list_api_call_traces(job_id=jid, limit=2000)
    http_traces = await repo.list_http_fetch_traces(job_id=jid, limit=2000)
    link_audits = await repo.list_phase2_link_audits(job_id=jid, limit=500)
    all_trees = await repo.list_site_trees(limit=2000)
    trees = [t for t in all_trees if (not target_domains or t.domain in target_domains)]
    all_playbooks = await repo.list_domain_playbooks(limit=500)
    playbooks = [pb for pb in all_playbooks if (not target_domains or pb.domain in target_domains)]
    profs = await repo.list_professors(domains=list(target_domains) if target_domains else None)
    all_reviews = await repo.list_needs_review(limit=2000)
    reviews = [r for r in all_reviews if (not target_domains or r.domain in target_domains)]

    jsonl_bytes = b""
    try:
        log_path = get_job_log_path(jid)
        if log_path.exists():
            jsonl_bytes = log_path.read_bytes()
    except Exception:
        jsonl_bytes = b""

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("job_summary.json", json.dumps(job_doc.model_dump(mode="json") if job_doc else {"job_id": jid}, ensure_ascii=False, indent=2))
        zf.writestr(f"{jid}.jsonl", jsonl_bytes)
        zf.writestr("api_call_traces.json", json.dumps([t.model_dump(mode="json") for t in api_traces], ensure_ascii=False, indent=2))
        zf.writestr("http_fetch_traces.json", json.dumps([t.model_dump(mode="json") for t in http_traces], ensure_ascii=False, indent=2))
        zf.writestr("phase2_link_audits.json", json.dumps([a.model_dump(mode="json") for a in link_audits], ensure_ascii=False, indent=2))
        zf.writestr("site_trees.json", json.dumps([t.model_dump(mode="json") for t in trees], ensure_ascii=False, indent=2))
        zf.writestr("domain_playbooks.json", json.dumps([p.model_dump(mode="json") for p in playbooks], ensure_ascii=False, indent=2))
        zf.writestr("professors.json", json.dumps([p.model_dump(mode="json") for p in profs], ensure_ascii=False, indent=2))
        zf.writestr("needs_review.json", json.dumps([r.model_dump(mode="json") for r in reviews], ensure_ascii=False, indent=2))

    return Response(
        content=zbuf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="run_{jid}_all_logs.zip"'},
    )


@router.get("/system/summary")
async def get_system_summary(request: Request):
    """Fast indexed count_documents() summary."""
    repo = _get_repo(request)
    from app.core.llm_router import llm_router
    summary = await repo.get_system_summary()
    summary["queue_state"] = llm_router.get_queue_state()
    return summary
