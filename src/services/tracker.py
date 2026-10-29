"""Open Tracking Service serving an invisible 1x1 GIF tracking pixel."""

from datetime import datetime, timezone
from typing import Dict, Optional
from src.core.logger import setup_logger
from src.models.telemetry import TrackingHit

logger = setup_logger("TrackerService")

# Binary representation of a 1x1 transparent GIF
TRANSPARENT_1X1_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
    b"\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00"
    b"\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class PixelTrackerService:
    """Manages pixel hit ingestion, first/last opened timestamps, and view count increments."""

    def __init__(self):
        # In-memory fast cache for telemetry before or alongside database writes
        self.hits_cache: Dict[str, TrackingHit] = {}

    def record_open(
        self,
        tracking_token: str,
        draft_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TrackingHit:
        """Records pixel read receipt, sets first_opened_at, and increments counter."""
        now = datetime.now(timezone.utc)
        resolved_draft_id = draft_id or tracking_token

        if tracking_token in self.hits_cache:
            hit = self.hits_cache[tracking_token]
            hit.open_count += 1
            hit.last_opened_at = now
            hit.ip_address = ip_address or hit.ip_address
            hit.user_agent = user_agent or hit.user_agent
            logger.info(f"Tracking Pixel HIT (repeat): Draft '{resolved_draft_id}' opened {hit.open_count} times.")
            return hit

        hit = TrackingHit(
            draft_id=resolved_draft_id,
            tracking_token=tracking_token,
            first_opened_at=now,
            last_opened_at=now,
            open_count=1,
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.hits_cache[tracking_token] = hit
        logger.info(f"Tracking Pixel HIT (FIRST OPEN): Draft '{resolved_draft_id}' read receipt confirmed at {now.isoformat()}.")
        return hit

    def get_hit_data(self, tracking_token: str) -> Optional[TrackingHit]:
        """Retrieves telemetry record for a tracking token."""
        return self.hits_cache.get(tracking_token)


tracker_service = PixelTrackerService()
