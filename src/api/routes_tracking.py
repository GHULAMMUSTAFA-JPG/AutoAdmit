"""Telemetry, open tracking pixel, and inbound response poller endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.routes_drafts import drafts_cache
from src.api.routes_professors import professors_cache
from src.config import settings
from src.core.logger import setup_logger
from src.models.draft import DraftStatus
from src.models.telemetry import CampaignAnalytics, InboundReply, TrackingHit
from src.services.imap_engine import imap_harvester
from src.services.smtp_engine import smtp_engine
from src.services.tracker import TRANSPARENT_1X1_GIF, tracker_service

router = APIRouter(prefix="/api/v1/track", tags=["Tracking"])
logger = setup_logger("TrackingAPI")


@router.get("/open/{tracking_token}")
def serve_tracking_pixel(tracking_token: str, request: Request):
    """
    Public open tracking endpoint. Serves an invisible 1x1 transparent GIF.
    Logs read receipts, first/last opened timestamps, and increments view count.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Match token to draft if possible
    matched_draft_id = None
    for d in drafts_cache.values():
        if d.tracking_token == tracking_token:
            matched_draft_id = d.id
            break

    tracker_service.record_open(
        tracking_token=tracking_token,
        draft_id=matched_draft_id,
        ip_address=client_ip,
        user_agent=user_agent
    )

    return Response(
        content=TRANSPARENT_1X1_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/analytics", response_model=CampaignAnalytics)
def get_campaign_analytics(user: str = Depends(get_current_user)):
    """Computes real-time telemetry metrics across the entire outreach pipeline."""
    drafts = list(drafts_cache.values())
    total_drafts = len(drafts)
    total_approved = len([d for d in drafts if d.status == DraftStatus.APPROVED])
    total_sent = len([d for d in drafts if d.status in [DraftStatus.SENT, DraftStatus.REPLIED]])
    total_replied = len([d for d in drafts if d.status == DraftStatus.REPLIED])

    # Calculate pixel hits
    total_opened = sum(hit.open_count for hit in tracker_service.hits_cache.values())

    # Calculate average reply latency
    replies = list(imap_harvester.cached_replies.values())
    avg_latency = 0.0
    if replies:
        avg_latency = sum(r.reply_latency_hours for r in replies) / len(replies)

    return CampaignAnalytics(
        total_professors_discovered=len(professors_cache),
        total_drafts_generated=total_drafts,
        total_drafts_approved=total_approved,
        total_sent=total_sent,
        total_delivered_250_ok=total_sent,
        total_opened_pixel=total_opened,
        total_replies_received=total_replied,
        average_reply_latency_hours=round(avg_latency, 1),
        master_gate_active=settings.SYSTEM_GATE_ACTIVE,
        sandbox_mode=settings.SANDBOX_MODE
    )


@router.post("/poll-replies", response_model=List[InboundReply])
async def poll_inbound_replies(user: str = Depends(get_current_user)):
    """Triggers IMAP scan against applicant inbox to detect professor replies."""
    # Build map of sent Message-IDs to drafts
    sent_map = {}
    for d in drafts_cache.values():
        if d.message_id:
            sent_map[d.message_id] = d

    detected = await imap_harvester.poll_inbox_sync(sent_map)
    return detected
