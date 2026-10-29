"""Telemetry, tracking pixel, and inbound response schemas."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class TrackingHit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    draft_id: str
    tracking_token: str
    first_opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    open_count: int = Field(default=1)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class InboundReply(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    draft_id: str
    message_id: str
    in_reply_to: str
    references: List[str] = Field(default_factory=list)
    from_email: str
    subject: str
    snippet: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reply_latency_hours: float = Field(default=0.0)


class CampaignAnalytics(BaseModel):
    total_professors_discovered: int = 0
    total_drafts_generated: int = 0
    total_drafts_approved: int = 0
    total_sent: int = 0
    total_delivered_250_ok: int = 0
    total_opened_pixel: int = 0
    total_replies_received: int = 0
    average_reply_latency_hours: float = 0.0
    master_gate_active: bool = True
    sandbox_mode: bool = True
