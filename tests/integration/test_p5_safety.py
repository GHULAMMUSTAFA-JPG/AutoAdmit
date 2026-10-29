"""Phase P5 Test: Multi-Layer Outbound Safety Gates and Master Kill-Switch."""

import pytest
from src.config import settings
from src.models.draft import DraftStatus, OutreachDraft
from src.services.smtp_engine import SMTPEngine, SecurityGateException


@pytest.mark.asyncio
async def test_p5_master_kill_switch_gate_1():
    """Verify Master Kill-Switch aborts send with 403 Forbidden and zero SMTP network traffic."""
    smtp = SMTPEngine()
    settings.SYSTEM_GATE_ACTIVE = True

    approved_draft = OutreachDraft(
        professor_id="prof-1",
        recipient_email="prof@tsinghua.edu.cn",
        recipient_name="Professor Wang",
        university="Tsinghua University",
        research_digest="Digest text",
        subject_line="Subject",
        body_text="Body text under 200 words",
        status=DraftStatus.APPROVED
    )

    with pytest.raises(SecurityGateException) as exc_info:
        await smtp.send_draft(approved_draft, dry_run=True)

    assert "Master Kill-Switch is ACTIVE" in str(exc_info.value)
    assert approved_draft.status == DraftStatus.APPROVED  # Not marked SENT


@pytest.mark.asyncio
async def test_p5_human_approval_gate_3():
    """Verify drafts in PENDING_REVIEW or REJECTED status are rejected by SMTP worker."""
    smtp = SMTPEngine()
    settings.SYSTEM_GATE_ACTIVE = False  # Deactivate master switch for this test

    pending_draft = OutreachDraft(
        professor_id="prof-2",
        recipient_email="prof@zju.edu.cn",
        recipient_name="Professor Chen",
        university="Zhejiang University",
        research_digest="Digest text",
        subject_line="Subject",
        body_text="Body text",
        status=DraftStatus.PENDING_REVIEW  # Unapproved!
    )

    with pytest.raises(SecurityGateException) as exc_info:
        await smtp.send_draft(pending_draft, dry_run=True)

    assert "not approved for dispatch" in str(exc_info.value)
    assert pending_draft.status == DraftStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_p5_sandbox_mode_gate_2():
    """Verify Sandbox Mode overrides recipient to TEST_RECIPIENT_EMAIL."""
    smtp = SMTPEngine()
    settings.SYSTEM_GATE_ACTIVE = False
    settings.SANDBOX_MODE = True
    settings.TEST_RECIPIENT_EMAIL = "my.personal.inbox@example.com"

    approved_draft = OutreachDraft(
        professor_id="prof-3",
        recipient_email="real_professor@tsinghua.edu.cn",
        recipient_name="Professor Wang",
        university="Tsinghua University",
        research_digest="Digest text",
        subject_line="Subject",
        body_text="Body text",
        status=DraftStatus.APPROVED
    )

    is_allowed, effective_recipient = smtp.check_safety_gates(approved_draft)
    assert is_allowed is True
    assert effective_recipient == "my.personal.inbox@example.com"
    assert effective_recipient != approved_draft.recipient_email

    # Dry run send
    success, _ = await smtp.send_draft(approved_draft, dry_run=True)
    assert success is True
    assert approved_draft.status == DraftStatus.SENT

    # Re-enable Master Kill-Switch after test to maintain fail-safe
    settings.SYSTEM_GATE_ACTIVE = True

