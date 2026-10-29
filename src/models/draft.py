"""Outreach email drafts and human review schemas."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DraftStatus(str, Enum):
    DRAFTED = "DRAFTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    REPLIED = "REPLIED"


class OutreachDraft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    professor_id: str = Field(..., description="Foreign key to FacultyProfile.id")
    recipient_email: str = Field(..., description="Target professor email")
    recipient_name: str = Field(..., description="Target professor name")
    university: str = Field(..., description="Target university name")
    department: str = Field(default="")
    research_digest: str = Field(..., description="2-3 sentence factual research digest from Gemini")
    subject_line: str = Field(..., description="Compelling customized subject line")
    body_text: str = Field(..., description="Plain-text cold email draft (<200 words)")
    body_html: Optional[str] = Field(default=None, description="HTML version with embedded tracking pixel")
    status: DraftStatus = Field(default=DraftStatus.PENDING_REVIEW, description="Default is locked to PENDING_REVIEW")
    rejection_reason: Optional[str] = None
    tracking_token: str = Field(default_factory=lambda: str(uuid.uuid4()), description="1x1 pixel tracking identifier")
    message_id: Optional[str] = Field(default=None, description="RFC 2822 Message-ID for thread matching")
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DraftApprovalRequest(BaseModel):
    subject_line: Optional[str] = None
    body_text: Optional[str] = None
    status: DraftStatus = Field(default=DraftStatus.APPROVED)
    scheduled_for: Optional[datetime] = None


class DraftRejectionRequest(BaseModel):
    rejection_reason: str

