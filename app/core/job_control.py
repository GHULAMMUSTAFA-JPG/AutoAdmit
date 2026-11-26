"""Cooperative background job cancellation registry and frozen per-run archive builder."""

import asyncio
from typing import Any

from app.core.logging import get_job_log_path, get_logger
from app.schemas.entities import RunArchiveDoc

logger = get_logger("core.job_control")

_ACTIVE_TASKS: dict[str, asyncio.Task[Any]] = {}
_CANCEL_EVENTS: dict[str, asyncio.Event] = {}


def register_job_task(job_id: str, task: asyncio.Task[Any]) -> None:
    """Tracks a running background job task and ensures a cancel event exists."""
    _ACTIVE_TASKS[job_id] = task
    _CANCEL_EVENTS.setdefault(job_id, asyncio.Event())

    def _cleanup(_: asyncio.Task[Any]) -> None:
        _ACTIVE_TASKS.pop(job_id, None)

    task.add_done_callback(_cleanup)


def ensure_cancel_event(job_id: str) -> asyncio.Event:
    return _CANCEL_EVENTS.setdefault(job_id, asyncio.Event())


def is_job_stopped(job_id: str) -> bool:
    ev = _CANCEL_EVENTS.get(job_id)
    return bool(ev and ev.is_set())


def request_job_stop(job_id: str) -> bool:
    """Signals cooperative cancellation and cancels the active asyncio.Task if running."""
    ev = _CANCEL_EVENTS.setdefault(job_id, asyncio.Event())
    ev.set()
    task = _ACTIVE_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()
        logger.info("job_task_cancel_requested", job_id=job_id)
        return True
    return False


def clear_job_control(job_id: str) -> None:
    _ACTIVE_TASKS.pop(job_id, None)
    _CANCEL_EVENTS.pop(job_id, None)


async def freeze_run_archive(repo: Any, job_id: str) -> RunArchiveDoc | None:
    """Freezes a complete per-run snapshot in MongoDB `run_archives` so later runs never overwrite past ZIPs."""
    try:
        job_doc = await repo.get_job(job_id)
        if not job_doc:
            return None
        target_domains = set(job_doc.target_domains or [])
        api_traces = await repo.list_api_call_traces(job_id=job_id, limit=2000)
        http_traces = await repo.list_http_fetch_traces(job_id=job_id, limit=2000)
        link_audits = await repo.list_phase2_link_audits(job_id=job_id, limit=500)
        all_trees = await repo.list_site_trees(limit=2000)
        trees = [t for t in all_trees if (not target_domains or t.domain in target_domains)]
        all_playbooks = await repo.list_domain_playbooks(limit=500)
        playbooks = [pb for pb in all_playbooks if (not target_domains or pb.domain in target_domains)]
        profs = await repo.list_professors(domains=list(target_domains) if target_domains else None)
        all_reviews = await repo.list_needs_review(limit=2000)
        reviews = [r for r in all_reviews if (not target_domains or r.domain in target_domains)]

        jsonl_text = ""
        try:
            lp = get_job_log_path(job_id)
            if lp.exists():
                jsonl_text = lp.read_text(encoding="utf-8", errors="replace")[:1_500_000]
        except Exception:
            jsonl_text = ""

        req = job_doc.request or {}
        regions = req.get("regions") or []
        region_str = ", ".join(regions) if isinstance(regions, list) and regions else "All Regions"
        mode_str = str((job_doc.scorecard or {}).get("mode") or ("TREE_ONLY" if job_id.startswith("tree_") else ("TREE_EXTRACT" if job_id.startswith("ext_") else "FULL_PIPELINE")))

        archive = RunArchiveDoc(
            job_id=job_id,
            mode=mode_str,
            region=region_str,
            status=job_doc.status,
            target_domains=list(job_doc.target_domains or []),
            professors_count=len(profs),
            traces_count=len(api_traces),
            reviews_count=len(reviews),
            snapshot_payload={
                "job_summary": job_doc.model_dump(mode="json"),
                "jsonl_text": jsonl_text,
                "api_call_traces": [t.model_dump(mode="json") for t in api_traces],
                "http_fetch_traces": [t.model_dump(mode="json") for t in http_traces],
                "phase2_link_audits": [a.model_dump(mode="json") for a in link_audits],
                "site_trees": [t.model_dump(mode="json") for t in trees],
                "domain_playbooks": [p.model_dump(mode="json") for p in playbooks],
                "professors": [p.model_dump(mode="json") for p in profs],
                "needs_review": [r.model_dump(mode="json") for r in reviews],
            },
        )
        await repo.upsert_run_archive(archive)
        return archive
    except Exception as exc:
        logger.warning("freeze_run_archive_failed", job_id=job_id, error=f"{type(exc).__name__}: {exc}")
        return None
