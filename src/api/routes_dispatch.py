"""Outbox Dispatcher, delivery scheduler, and CST operational window endpoints."""

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.routes_drafts import drafts_cache
from src.config import settings
from src.core.database import db_manager
from src.core.logger import setup_logger
from src.models.draft import DraftStatus, OutreachDraft
from src.services.smtp_engine import SecurityGateException, smtp_engine

router = APIRouter(prefix="/api/v1/dispatch", tags=["Dispatch"])
logger = setup_logger("DispatchAPI")


class BatchSendRequest(BaseModel):
    draft_ids: Optional[List[str]] = None
    send_all_approved: bool = False
    dry_run: bool = False
    ignore_cst_window: bool = False


@router.get("/cst-status")
def get_cst_status(user: str = Depends(get_current_user)):
    """Returns live China Standard Time (CST, UTC+8) and window operational status."""
    utc_now = datetime.now(timezone.utc)
    cst_now = utc_now + timedelta(hours=8)
    in_window = smtp_engine.is_within_cst_window()

    return {
        "utc_time": utc_now.isoformat(),
        "cst_time": cst_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "is_within_cst_window": in_window,
        "operational_window": f"{settings.CST_SEND_START_HOUR:02d}:00 - {settings.CST_SEND_END_HOUR:02d}:{settings.CST_SEND_END_MINUTE:02d} CST",
        "master_gate_active": settings.SYSTEM_GATE_ACTIVE,
        "sandbox_mode": settings.SANDBOX_MODE,
        "hourly_sent": len(smtp_engine.sent_history)
    }


@router.get("/queue", response_model=List[OutreachDraft])
async def get_dispatch_queue(user: str = Depends(get_current_user)):
    """Returns drafts currently staged for dispatch (status == APPROVED)."""
    if db_manager.is_connected and db_manager.db is not None:
        cursor = db_manager.get_collection("outreach_drafts").find({"status": DraftStatus.APPROVED.value})
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(OutreachDraft(**doc))
        if results:
            return results

    return [d for d in drafts_cache.values() if d.status == DraftStatus.APPROVED]


@router.post("/send-single/{draft_id}", response_model=OutreachDraft)
async def send_single_draft(
    draft_id: str,
    dry_run: bool = False,
    ignore_cst_window: bool = False,
    user: str = Depends(get_current_user)
):
    """Dispatches a single approved draft through safety gates."""
    # Find draft
    draft = None
    if db_manager.is_connected and db_manager.db is not None:
        doc = await db_manager.get_collection("outreach_drafts").find_one({"id": draft_id})
        if doc:
            doc.pop("_id", None)
            draft = OutreachDraft(**doc)

    if not draft and draft_id in drafts_cache:
        draft = drafts_cache[draft_id]

    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")

    # Check CST Window unless ignored for testing
    if not ignore_cst_window and not smtp_engine.is_within_cst_window():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outside operational CST sending window (09:00 - 16:30 CST). Sending paused."
        )

    try:
        success, message_id = await smtp_engine.send_draft(draft, dry_run=dry_run)
        if not success:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit reached.")

        drafts_cache[draft.id] = draft
        if db_manager.is_connected and db_manager.db is not None:
            await db_manager.get_collection("outreach_drafts").update_one(
                {"id": draft.id},
                {"$set": draft.model_dump()}
            )
        return draft
    except SecurityGateException as sge:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(sge))
    except Exception as e:
        logger.error(f"Failed to dispatch draft {draft.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"SMTP dispatch error: {e}")


@router.post("/send-batch", response_model=List[OutreachDraft])
async def send_batch_queue(
    request: BatchSendRequest,
    user: str = Depends(get_current_user)
):
    """Dispatches queued approved drafts with randomized jitter pauses (90-240s)."""
    if not request.ignore_cst_window and not smtp_engine.is_within_cst_window():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outside operational CST sending window (09:00 - 16:30 CST)."
        )

    # Gather target drafts
    candidates: List[OutreachDraft] = []
    if request.send_all_approved:
        candidates = await get_dispatch_queue(user)
    elif request.draft_ids:
        for did in request.draft_ids:
            if did in drafts_cache and drafts_cache[did].status == DraftStatus.APPROVED:
                candidates.append(drafts_cache[did])

    if not candidates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No approved drafts selected for dispatch.")

    dispatched = await smtp_engine.send_batch(candidates, apply_jitter=not request.dry_run)
    return dispatched
