"""Email drafts review workspace and approval staging endpoints."""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.core.database import db_manager
from src.core.logger import setup_logger
from src.models.draft import DraftApprovalRequest, DraftRejectionRequest, DraftStatus, OutreachDraft
from src.models.professor import FacultyProfile
from src.services.llm_agent import llm_agent

router = APIRouter(prefix="/api/v1/drafts", tags=["Drafts"])
logger = setup_logger("DraftsAPI")

# Memory store for active drafts
drafts_cache: dict = {}


class UpdateDraftRequest(BaseModel):
    subject_line: Optional[str] = None
    body_text: Optional[str] = None


@router.get("", response_model=List[OutreachDraft])
async def list_drafts(
    status_filter: Optional[str] = Query(None, alias="status"),
    user: str = Depends(get_current_user)
):
    """Lists drafts filtered by status (PENDING_REVIEW, APPROVED, SENT, REPLIED)."""
    if db_manager.is_connected and db_manager.db is not None:
        query = {}
        if status_filter:
            query["status"] = status_filter
        cursor = db_manager.get_collection("outreach_drafts").find(query)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(OutreachDraft(**doc))
        if results:
            return results

    results = list(drafts_cache.values())
    if status_filter:
        results = [d for d in results if d.status == status_filter]
    return results


@router.get("/{draft_id}", response_model=OutreachDraft)
async def get_draft(draft_id: str, user: str = Depends(get_current_user)):
    """Retrieves specific draft for split-pane review."""
    if db_manager.is_connected and db_manager.db is not None:
        doc = await db_manager.get_collection("outreach_drafts").find_one({"id": draft_id})
        if doc:
            doc.pop("_id", None)
            return OutreachDraft(**doc)

    if draft_id in drafts_cache:
        return drafts_cache[draft_id]

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")


@router.put("/{draft_id}", response_model=OutreachDraft)
async def update_draft(
    draft_id: str,
    update_data: UpdateDraftRequest,
    user: str = Depends(get_current_user)
):
    """Inline editor: Updates draft subject line or body text."""
    draft = await get_draft(draft_id, user)

    if update_data.subject_line is not None:
        draft.subject_line = update_data.subject_line
    if update_data.body_text is not None:
        llm_agent.validate_draft_guardrails(update_data.body_text)
        draft.body_text = update_data.body_text

    draft.updated_at = datetime.now(timezone.utc)
    drafts_cache[draft.id] = draft

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("outreach_drafts").update_one(
            {"id": draft.id},
            {"$set": draft.model_dump()}
        )

    logger.info(f"Draft '{draft.id}' updated inline.")
    return draft


@router.post("/{draft_id}/approve", response_model=OutreachDraft)
async def approve_draft(
    draft_id: str,
    approval: Optional[DraftApprovalRequest] = None,
    user: str = Depends(get_current_user)
):
    """Promotes draft from PENDING_REVIEW to APPROVED for SMTP dispatch staging."""
    draft = await get_draft(draft_id, user)

    if approval:
        if approval.subject_line:
            draft.subject_line = approval.subject_line
        if approval.body_text:
            llm_agent.validate_draft_guardrails(approval.body_text)
            draft.body_text = approval.body_text
        if approval.scheduled_for:
            draft.scheduled_for = approval.scheduled_for

    draft.status = DraftStatus.APPROVED
    draft.updated_at = datetime.now(timezone.utc)
    drafts_cache[draft.id] = draft

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("outreach_drafts").update_one(
            {"id": draft.id},
            {"$set": draft.model_dump()}
        )

    logger.info(f"HUMAN APPROVAL GRANTED: Draft '{draft.id}' to '{draft.recipient_name}' staged as APPROVED.")
    return draft


@router.post("/{draft_id}/reject", response_model=OutreachDraft)
async def reject_draft(
    draft_id: str,
    rejection: DraftRejectionRequest,
    user: str = Depends(get_current_user)
):
    """Marks draft as REJECTED with human explanation."""
    draft = await get_draft(draft_id, user)
    draft.status = DraftStatus.REJECTED
    draft.rejection_reason = rejection.rejection_reason
    draft.updated_at = datetime.now(timezone.utc)
    drafts_cache[draft.id] = draft

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("outreach_drafts").update_one(
            {"id": draft.id},
            {"$set": draft.model_dump()}
        )

    logger.info(f"Draft '{draft.id}' REJECTED. Reason: {rejection.rejection_reason}")
    return draft


@router.post("/{draft_id}/regenerate", response_model=OutreachDraft)
async def regenerate_draft(
    draft_id: str,
    user: str = Depends(get_current_user)
):
    """Regenerates research digest and cold outreach draft via Gemini LLM."""
    draft = await get_draft(draft_id, user)

    mock_profile = FacultyProfile(
        id=draft.professor_id,
        name=draft.recipient_name,
        email=draft.recipient_email,
        university=draft.university,
        department=draft.department,
        qualification="博导",
        source_url="https://verified.edu.cn",
        content_hash="regenerated",
        worker_id="regen"
    )

    digest = await llm_agent.generate_research_digest(mock_profile)
    new_draft = await llm_agent.generate_outreach_draft(mock_profile, digest)
    new_draft.id = draft.id  # Retain original ID
    new_draft.tracking_token = draft.tracking_token
    drafts_cache[new_draft.id] = new_draft

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("outreach_drafts").update_one(
            {"id": new_draft.id},
            {"$set": new_draft.model_dump()}
        )

    logger.info(f"Regenerated draft '{draft.id}' via Gemini LLM.")
    return new_draft

