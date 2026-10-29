"""Inbound Tracking & Response Harvester via IMAP SSL header cross-referencing."""

import asyncio
import email
from email.header import decode_header
import imaplib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import uuid

from src.config import settings
from src.core.logger import setup_logger
from src.models.draft import DraftStatus, OutreachDraft
from src.models.telemetry import InboundReply

logger = setup_logger("IMAPHarvester")


def decode_str(header_value: Optional[str]) -> str:
    """Decodes MIME encoded header strings into standard unicode."""
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            result.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(fragment))
    return " ".join(result).strip()


class IMAPResponseHarvester:
    """Continuously monitors applicant inbox for professor replies by cross-referencing message headers."""

    def __init__(self):
        self.cached_replies: Dict[str, InboundReply] = {}

    def match_reply_headers(
        self,
        inbound_headers: dict,
        sent_drafts_map: Dict[str, OutreachDraft]
    ) -> Optional[Tuple[OutreachDraft, InboundReply]]:
        """
        Cross-references In-Reply-To and References headers with sent Message-IDs.
        Returns matching (draft, InboundReply) or None.
        """
        in_reply_to = inbound_headers.get("In-Reply-To", "").strip()
        references = inbound_headers.get("References", "")
        ref_tokens = references.split() if references else []

        matched_draft: Optional[OutreachDraft] = None

        # Check in_reply_to first
        if in_reply_to and in_reply_to in sent_drafts_map:
            matched_draft = sent_drafts_map[in_reply_to]
        else:
            # Check references list
            for ref in ref_tokens:
                ref_clean = ref.strip()
                if ref_clean in sent_drafts_map:
                    matched_draft = sent_drafts_map[ref_clean]
                    break

        if not matched_draft:
            return None

        # Calculate reply latency
        now = datetime.now(timezone.utc)
        latency = 0.0
        if matched_draft.sent_at:
            latency = max(0.0, (now - matched_draft.sent_at).total_seconds() / 3600.0)

        reply = InboundReply(
            id=str(uuid.uuid4()),
            draft_id=matched_draft.id,
            message_id=inbound_headers.get("Message-ID", f"<{uuid.uuid4()}@inbound>"),
            in_reply_to=in_reply_to,
            references=ref_tokens,
            from_email=inbound_headers.get("From", ""),
            subject=inbound_headers.get("Subject", "Re: Admission Outreach"),
            snippet=inbound_headers.get("Snippet", "Dear Applicant, thank you for your email..."),
            received_at=now,
            reply_latency_hours=round(latency, 2)
        )

        matched_draft.status = DraftStatus.REPLIED
        self.cached_replies[reply.id] = reply
        logger.info(
            f"PROFESSOR REPLY DETECTED! Draft '{matched_draft.id}' to '{matched_draft.recipient_name}' at "
            f"{matched_draft.university}. Latency: {reply.reply_latency_hours:.1f} hours."
        )
        return matched_draft, reply

    async def poll_inbox_sync(self, sent_drafts_map: Dict[str, OutreachDraft]) -> List[InboundReply]:
        """Polls IMAP server over SSL (or simulated test box if unconfigured)."""
        if not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
            logger.info("IMAP credentials not configured. Harvester operating in test/standby mode.")
            return list(self.cached_replies.values())

        loop = asyncio.get_running_loop()

        def _fetch_imap():
            detected = []
            try:
                with imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT) as mail:
                    mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
                    mail.select("INBOX")
                    # Search for unread or recent messages
                    status, message_numbers = mail.search(None, "UNSEEN")
                    if status != "OK" or not message_numbers[0]:
                        return detected

                    for num in message_numbers[0].split():
                        _, msg_data = mail.fetch(num, "(RFC822.HEADER)")
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                headers = {
                                    "Message-ID": msg.get("Message-ID", ""),
                                    "In-Reply-To": msg.get("In-Reply-To", ""),
                                    "References": msg.get("References", ""),
                                    "From": decode_str(msg.get("From")),
                                    "Subject": decode_str(msg.get("Subject")),
                                }
                                match = self.match_reply_headers(headers, sent_drafts_map)
                                if match:
                                    detected.append(match[1])
            except Exception as e:
                logger.error(f"Error polling IMAP inbox: {e}")
            return detected

        return await loop.run_in_executor(None, _fetch_imap)


imap_harvester = IMAPResponseHarvester()
