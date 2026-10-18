import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union
from pydantic import BaseModel, Field, HttpUrl


class SendSMSPayload(BaseModel):
    """Payload to send an SMS."""
    sender_id: str = Field(
        ...,
        min_length=1,
        max_length=15,
        description="Alphanumeric Sender ID (max 11 chars) or Shortcode/E.164 (max 15 chars)",
        examples=["MYBRAND", "1448", "+12025550143"],
    )
    recipient: str = Field(
        ...,
        pattern=r"^\+?[1-9]\d{6,14}$",
        description="E.164 format phone number (e.g. +12025550143)",
        examples=["+12025550143"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1600,
        description="Text content of the SMS message",
    )
    dlr_callback_url: Optional[str] = Field(
        None,
        description="Optional custom webhook URL for Delivery Receipts for this specific message",
    )


class SMSResponse(BaseModel):
    """Response returned upon message queuing."""
    id: Union[str, uuid.UUID]
    status: str
    message_id: Optional[str] = None
    encoding: str
    segments: int
    cost: Decimal
    recipient: str
    sender_id: str
    created_at: datetime


class SMSDetailResponse(BaseModel):
    """Full detail of a stored SMS message."""
    id: Union[str, uuid.UUID]
    tenant_id: Union[str, uuid.UUID]
    message_id: Optional[str]
    sender_id: str
    recipient: str
    content: str
    encoding: str
    segments: int
    total_cost: Decimal
    status: str
    error_code: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None


class SMSListResponse(BaseModel):
    """Paginated list of messages."""
    total: int
    page: int
    limit: int
    items: list[SMSDetailResponse]


class TenantWebhookNotification(BaseModel):
    """Schema dispatched to customer webhook upon DLR receipt."""
    event: str = "message.status_update"
    message_id: str
    jasmin_msgid: Optional[str]
    recipient: str
    sender_id: str
    status: str
    error_code: Optional[str] = None
    delivered_at: Optional[datetime] = None
