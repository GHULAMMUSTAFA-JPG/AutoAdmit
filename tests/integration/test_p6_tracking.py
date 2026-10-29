"""Phase P6 Test: 1x1 Pixel Tracking Receipts and Inbound IMAP Header Matching."""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from src.services.tracker import tracker_service, TRANSPARENT_1X1_GIF
from src.services.imap_engine import imap_harvester
from src.models.draft import DraftStatus, OutreachDraft


def test_p6_tracking_pixel_endpoint(client: TestClient):
    """Verify 1x1 transparent GIF is returned and open telemetry increments."""
    token = "test-token-uuid-12345"

    # 1. First open
    res1 = client.get(f"/api/v1/track/open/{token}")
    assert res1.status_code == 200
    assert res1.headers["content-type"] == "image/gif"
    assert res1.content == TRANSPARENT_1X1_GIF

    hit1 = tracker_service.get_hit_data(token)
    assert hit1 is not None
    assert hit1.open_count == 1
    first_open_time = hit1.first_opened_at

    # 2. Second open (Repeat view)
    res2 = client.get(f"/api/v1/track/open/{token}")
    assert res2.status_code == 200
    hit2 = tracker_service.get_hit_data(token)
    assert hit2.open_count == 2
    assert hit2.first_opened_at == first_open_time


def test_p6_imap_inbound_reply_header_matching():
    """Verify IMAP poller cross-references In-Reply-To to transition draft status to REPLIED."""
    sent_time = datetime.now(timezone.utc) - timedelta(hours=3, minutes=15)
    sent_message_id = "<outreach-draft-999@autoadmit.local>"

    sent_draft = OutreachDraft(
        id="draft-999",
        professor_id="prof-999",
        recipient_email="prof.li@pku.edu.cn",
        recipient_name="Professor Li",
        university="Peking University",
        research_digest="Digest",
        subject_line="Prospective CSC Master's Student",
        body_text="Body",
        status=DraftStatus.SENT,
        sent_at=sent_time,
        message_id=sent_message_id
    )

    sent_drafts_map = {sent_message_id: sent_draft}

    # Simulate an incoming email from the professor replying to the thread
    inbound_headers = {
        "Message-ID": "<reply-from-prof@mail.pku.edu.cn>",
        "In-Reply-To": sent_message_id,
        "References": f"{sent_message_id}",
        "From": "Professor Li <prof.li@pku.edu.cn>",
        "Subject": "Re: Prospective CSC Master's Student",
        "Snippet": "Dear Alex, I reviewed your CV and would like to schedule a Zoom interview next Tuesday."
    }

    match_result = imap_harvester.match_reply_headers(inbound_headers, sent_drafts_map)
    assert match_result is not None

    matched_draft, inbound_reply = match_result
    assert matched_draft.status == DraftStatus.REPLIED
    assert inbound_reply.draft_id == "draft-999"
    assert inbound_reply.in_reply_to == sent_message_id
    assert 3.0 <= inbound_reply.reply_latency_hours <= 3.5

