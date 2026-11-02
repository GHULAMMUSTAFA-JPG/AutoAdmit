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
        return results

    # Fallback to in-memory cache when MongoDB is offline
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


class BatchGenerateDraftsRequest(BaseModel):
    professor_ids: Optional[List[str]] = None
    discipline: str = "Computer Science"
    max_workers: int = 3


class BulkApproveRequest(BaseModel):
    draft_ids: Optional[List[str]] = None
    max_words: int = 200


@router.post("/generate-batch", response_model=List[OutreachDraft])
async def generate_drafts_batch_endpoint(
    request: BatchGenerateDraftsRequest,
    user: str = Depends(get_current_user)
):
    """
    Batch-generates factual research digests and high-conversion cold outreach drafts
    using Gemini LLM across targeted professors with 1-3 parallel workers.
    """
    import asyncio

    target_profs: List[FacultyProfile] = []
    if request.professor_ids:
        if db_manager.is_connected and db_manager.db is not None:
            cursor = db_manager.get_collection("professors").find({"id": {"$in": request.professor_ids}})
            async for doc in cursor:
                doc.pop("_id", None)
                target_profs.append(FacultyProfile(**doc))
    else:
        # Default: take up to 30 pending professors with verified emails
        if db_manager.is_connected and db_manager.db is not None:
            cursor = db_manager.get_collection("professors").find({"email": {"$regex": r"@.*\.edu\.cn"}}).limit(30)
            async for doc in cursor:
                doc.pop("_id", None)
                target_profs.append(FacultyProfile(**doc))

    if not target_profs:
        return []

    worker_pool = min(3, max(1, request.max_workers))
    sem = asyncio.Semaphore(worker_pool)

    async def _process_single_prof(prof: FacultyProfile) -> Optional[OutreachDraft]:
        async with sem:
            try:
                digest = await llm_agent.generate_research_digest(prof)
                draft = await llm_agent.generate_outreach_draft(prof, digest)
                drafts_cache[draft.id] = draft
                if db_manager.is_connected and db_manager.db is not None:
                    await db_manager.get_collection("outreach_drafts").update_one(
                        {"professor_id": prof.id},
                        {"$set": draft.model_dump()},
                        upsert=True
                    )
                return draft
            except Exception as err:
                logger.error(f"Failed to generate draft for professor {prof.name} ({prof.id}): {err}")
                return None

    results = await asyncio.gather(*[_process_single_prof(p) for p in target_profs])
    return [r for r in results if r is not None]


@router.post("/bulk-approve")
async def bulk_approve_drafts_endpoint(
    request: BulkApproveRequest,
    user: str = Depends(get_current_user)
):
    """
    Bulk-promotes all eligible PENDING_REVIEW drafts with word count <= max_words
    to APPROVED status so they are staged for outbound SMTP dispatch.
    """
    approved_count = 0
    now = datetime.now(timezone.utc)

    filter_query: dict = {"status": DraftStatus.PENDING_REVIEW}
    if request.draft_ids:
        filter_query["id"] = {"$in": request.draft_ids}

    if db_manager.is_connected and db_manager.db is not None:
        cursor = db_manager.get_collection("outreach_drafts").find(filter_query)
        async for doc in cursor:
            body = doc.get("body_text", "")
            words = len(body.split())
            if words <= request.max_words:
                await db_manager.get_collection("outreach_drafts").update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": DraftStatus.APPROVED, "approved_at": now}}
                )
                approved_count += 1
                if doc.get("id") in drafts_cache:
                    drafts_cache[doc["id"]].status = DraftStatus.APPROVED
                    drafts_cache[doc["id"]].approved_at = now
    else:
        for d in drafts_cache.values():
            if d.status == DraftStatus.PENDING_REVIEW and len(d.body_text.split()) <= request.max_words:
                d.status = DraftStatus.APPROVED
                d.approved_at = now
                approved_count += 1

    logger.info(f"Bulk-approved {approved_count} drafts for outbound dispatch.")
    return {"approved_count": approved_count, "status": "success"}

