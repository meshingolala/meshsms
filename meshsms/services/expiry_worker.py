import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.config import settings
from meshsms.models.message import SMSMessage

logger = logging.getLogger("meshsms.expiry_worker")


class ExpiryWorker:
    """Sweeps and marks messages that have timed out waiting for a terminal DLR as EXPIRED."""

    @staticmethod
    async def expire_stale_messages(
        db: AsyncSession,
        max_age_hours: Optional[int] = None,
    ) -> int:
        """
        Updates messages in 'SENT' or 'QUEUED' state older than max_age_hours to 'EXPIRED'.
        Returns the number of expired messages.
        """
        hours = max_age_hours or settings.DLR_EXPIRY_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        logger.info("Running DLR expiry sweep for messages older than %s hours (cutoff: %s)", hours, cutoff)

        stmt = (
            update(SMSMessage)
            .where(
                SMSMessage.status.in_(["SENT", "QUEUED"]),
                SMSMessage.created_at < cutoff,
            )
            .values(
                status="EXPIRED",
                error_code="TIMEOUT",
            )
        )

        result = await db.execute(stmt)
        count = result.rowcount
        await db.commit()

        logger.info("DLR expiry sweep complete: %d messages marked EXPIRED", count)
        return count
