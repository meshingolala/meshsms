import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from meshsms.models.message import SMSMessage
from meshsms.models.tenant import Tenant
from meshsms.schemas.sms import TenantWebhookNotification

logger = logging.getLogger("meshsms.dlr_service")

# Exact required ACK response body for Jasmin SMS Gateway
JASMIN_ACK_RESPONSE = "ACK/Jasmin"

# Recognized terminal statuses in SMPP
TERMINAL_STATUSES = {"DELIVRD", "UNDELIV", "EXPIRED", "DELETER", "REJECTD"}


class DLRService:
    """Service to process carrier Delivery Receipts and notify tenants."""

    @staticmethod
    async def process_dlr(
        db: AsyncSession,
        jasmin_msgid: str,
        message_status: str,
        error_code: Optional[str] = None,
        done_date: Optional[str] = None,
    ) -> Optional[SMSMessage]:
        """
        Updates the message status in the database according to the carrier DLR.
        """
        logger.info(
            "Processing DLR: msgid=%s, status=%s, err=%s, donedate=%s",
            jasmin_msgid, message_status, error_code, done_date
        )

        # Lookup message with tenant loaded for webhook dispatch
        stmt = (
            select(SMSMessage)
            .options(selectinload(SMSMessage.tenant))
            .where(SMSMessage.jasmin_msgid == jasmin_msgid)
        )
        result = await db.execute(stmt)
        message = result.scalar_one_or_none()

        if not message:
            logger.warning("Received DLR for unknown jasmin_msgid: %s", jasmin_msgid)
            return None

        # Update fields
        message.status = message_status.upper() if message_status else "UNKNOWN"
        message.error_code = error_code if (error_code and error_code != "000") else None

        if message.status == "DELIVRD":
            message.delivered_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(message)
        logger.info("Message %s status updated to %s", message.id, message.status)
        return message

    @staticmethod
    async def dispatch_tenant_webhook(
        webhook_url: str,
        notification: TenantWebhookNotification,
    ) -> bool:
        """
        Sends an asynchronous webhook notification to the tenant's configured endpoint.
        """
        if not webhook_url:
            return False

        logger.info("Dispatching tenant webhook to %s for msg %s", webhook_url, notification.message_id)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    webhook_url,
                    json=notification.model_dump(mode="json"),
                    headers={"Content-Type": "application/json", "User-Agent": "MeshSMS-Webhook-Notifier/1.0"},
                )
            if resp.status_code in (200, 201, 202, 204):
                logger.info("Successfully delivered webhook for msg %s", notification.message_id)
                return True
            else:
                logger.warning(
                    "Tenant webhook endpoint %s returned status %s",
                    webhook_url, resp.status_code
                )
                return False
        except Exception as exc:
            logger.error("Failed to post webhook to %s: %s", webhook_url, exc)
            return False
