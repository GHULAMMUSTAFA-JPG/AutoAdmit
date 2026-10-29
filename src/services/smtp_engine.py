"""Outbound SMTP Engine featuring 3-Layer Safety Gates, CST Smart Scheduling, and Jitter Control."""

import asyncio
import email
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from pathlib import Path
import random
import smtplib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from src.config import settings
from src.core.logger import setup_logger
from src.models.draft import DraftStatus, OutreachDraft

logger = setup_logger("SMTPEngine")


class SecurityGateException(Exception):
    """Raised when an outbound transmission attempt is blocked by a safety gate."""
    pass


class SMTPEngine:
    """Outbound email transport with multi-layer safety gates, CST scheduling, and jitter control."""

    def __init__(self):
        self.sent_history: List[datetime] = []

    def check_safety_gates(self, draft: OutreachDraft) -> Tuple[bool, str]:
        """
        Evaluates the three defense-in-depth safety gates.
        Returns (is_allowed, effective_recipient). Raises SecurityGateException if blocked.
        """
        # Gate 1: Master Kill-Switch
        if settings.SYSTEM_GATE_ACTIVE:
            logger.error("GATE 1 VIOLATION: Master Kill-Switch is ACTIVE. Outbound SMTP sockets blocked.")
            raise SecurityGateException("403 Forbidden: Master Kill-Switch is ACTIVE. No outbound emails permitted.")

        # Gate 3: Explicit Human Approval Check
        if draft.status != DraftStatus.APPROVED:
            logger.error(f"GATE 3 VIOLATION: Draft '{draft.id}' has status '{draft.status}'. Only APPROVED drafts can be sent.")
            raise SecurityGateException(f"Draft not approved for dispatch (Status: {draft.status}).")

        # Gate 2: Sandbox / Test Mode
        if settings.SANDBOX_MODE:
            effective_recipient = settings.TEST_RECIPIENT_EMAIL
            logger.info(f"GATE 2 (SANDBOX ACTIVE): Overriding recipient '{draft.recipient_email}' -> '{effective_recipient}'.")
            return True, effective_recipient

        return True, draft.recipient_email

    def is_within_cst_window(self) -> bool:
        """
        Validates whether current time falls within China Standard Time (CST, UTC+8) working hours:
        09:00 - 16:30 CST.
        """
        cst_time = datetime.now(timezone.utc) + timedelta(hours=8)
        current_hour = cst_time.hour
        current_minute = cst_time.minute

        start_ok = current_hour >= settings.CST_SEND_START_HOUR
        end_ok = (current_hour < settings.CST_SEND_END_HOUR) or (
            current_hour == settings.CST_SEND_END_HOUR and current_minute <= settings.CST_SEND_END_MINUTE
        )
        return start_ok and end_ok

    def check_rate_limits(self) -> bool:
        """Enforces max 8-10 emails/hour and max 25 emails/day."""
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        recent_hour = [t for t in self.sent_history if t > one_hour_ago]
        recent_day = [t for t in self.sent_history if t > one_day_ago]

        if len(recent_hour) >= settings.MAX_EMAILS_PER_HOUR:
            logger.warning(f"Hourly rate limit reached ({len(recent_hour)}/{settings.MAX_EMAILS_PER_HOUR}). Pausing dispatch.")
            return False

        if len(recent_day) >= settings.MAX_EMAILS_PER_DAY:
            logger.warning(f"Daily rate limit reached ({len(recent_day)}/{settings.MAX_EMAILS_PER_DAY}). Pausing dispatch.")
            return False

        return True

    def build_email_message(self, draft: OutreachDraft, effective_recipient: str) -> MIMEMultipart:
        """Constructs multipart email with HTML tracking pixel, headers, and PDF attachments."""
        msg = MIMEMultipart("mixed")
        msg["Subject"] = Header(draft.subject_line, "utf-8")
        msg["From"] = f"{settings.SENDER_NAME} <{settings.SENDER_EMAIL or settings.SMTP_USERNAME}>"
        msg["To"] = effective_recipient
        msg["Date"] = email.utils.formatdate(localtime=True)

        # RFC 2822 Message-ID for tracking replies
        message_id = f"<{draft.id}@{settings.SMTP_HOST}>"
        msg["Message-ID"] = message_id
        draft.message_id = message_id

        # Diagnostic sandbox headers
        if settings.SANDBOX_MODE:
            msg["X-AutoAdmit-Sandbox"] = "ACTIVE"
            msg["X-AutoAdmit-Original-Recipient"] = draft.recipient_email
            msg["X-AutoAdmit-Professor"] = draft.recipient_name
            msg["X-AutoAdmit-University"] = draft.university

        # Embed Tracking Pixel into HTML alternative
        tracking_pixel_url = f"{settings.TRACKING_BASE_URL.rstrip('/')}/api/v1/track/open/{draft.tracking_token}"
        pixel_img_tag = f'<br/><img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none;" />'

        alt_part = MIMEMultipart("alternative")
        text_part = MIMEText(draft.body_text, "plain", "utf-8")
        alt_part.attach(text_part)

        html_content = draft.body_html or draft.body_text.replace("\n", "<br/>")
        html_content_with_pixel = f"<div>{html_content}</div>{pixel_img_tag}"
        draft.body_html = html_content_with_pixel
        html_part = MIMEText(html_content_with_pixel, "html", "utf-8")
        alt_part.attach(html_part)

        msg.attach(alt_part)

        # Optional PDF CV Attachment
        if settings.CV_PATH and Path(settings.CV_PATH).is_file():
            try:
                with open(settings.CV_PATH, "rb") as f:
                    pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
                    pdf_attachment.add_header("Content-Disposition", "attachment", filename=Path(settings.CV_PATH).name)
                    msg.attach(pdf_attachment)
            except Exception as e:
                logger.warning(f"Could not attach CV from {settings.CV_PATH}: {e}")

        return msg

    async def send_draft(self, draft: OutreachDraft, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Executes single email dispatch through all safety gates with socket safety.
        Returns (success, message_id).
        """
        # Step 1: Check safety gates
        _, effective_recipient = self.check_safety_gates(draft)

        # Step 2: Rate limits check
        if not self.check_rate_limits():
            return False, "Rate limit reached"

        # Step 3: Build RFC 2822 message
        msg = self.build_email_message(draft, effective_recipient)

        if dry_run or not settings.SMTP_USERNAME:
            logger.info(f"[DRY RUN / MOCK SMTP] Dispatched to {effective_recipient} with Message-ID {draft.message_id}")
            draft.status = DraftStatus.SENT
            draft.sent_at = datetime.now(timezone.utc)
            self.sent_history.append(datetime.now(timezone.utc))
            return True, draft.message_id or ""

        # Step 4: Actual SMTP dispatch
        loop = asyncio.get_running_loop()
        def _sync_send():
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

        await loop.run_in_executor(None, _sync_send)

        draft.status = DraftStatus.SENT
        draft.sent_at = datetime.now(timezone.utc)
        self.sent_history.append(datetime.now(timezone.utc))
        logger.info(f"Delivered email to {effective_recipient} (Message-ID: {draft.message_id})")
        return True, draft.message_id or ""

    async def send_batch(self, drafts: List[OutreachDraft], apply_jitter: bool = True) -> List[OutreachDraft]:
        """Dispatches an approved batch applying randomized pauses (90-240s) between successive sends."""
        dispatched = []
        for i, draft in enumerate(drafts):
            try:
                success, _ = await self.send_draft(draft)
                if success:
                    dispatched.append(draft)

                # Apply jitter between sends (skip after final item)
                if apply_jitter and i < len(drafts) - 1:
                    jitter = random.uniform(settings.JITTER_MIN_SECONDS, settings.JITTER_MAX_SECONDS)
                    logger.info(f"Applying safety jitter: Sleeping {jitter:.1f} seconds before next send...")
                    await asyncio.sleep(jitter)
            except SecurityGateException as sge:
                logger.error(f"Batch halted due to security gate: {sge}")
                break
            except Exception as e:
                logger.error(f"Error sending draft {draft.id}: {e}")
                # Continue with next draft without interrupting whole campaign

        return dispatched


smtp_engine = SMTPEngine()
