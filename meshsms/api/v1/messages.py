import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.api.deps import get_current_tenant
from meshsms.database import get_db
from meshsms.models.tenant import Tenant
from meshsms.models.message import SMSMessage
from meshsms.schemas.sms import (
    SendSMSPayload,
    SMSResponse,
    SMSDetailResponse,
    SMSListResponse,
)
from meshsms.services.encoding import calculate_sms_metrics
from meshsms.services.billing import BillingService, InsufficientBalanceError
from meshsms.services.jasmin_client import jasmin_client, JasminRouterError

logger = logging.getLogger("meshsms.api.messages")

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", response_model=SMSResponse, status_code=status.HTTP_201_CREATED)
async def send_sms(
    payload: SendSMSPayload,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Submits an outbound SMS message (Mobile Terminated - MT).
    
    1. Validates sender ID and recipient format.
    2. Calculates encoding (GSM-7 vs UCS-2) and exact segments.
    3. Atomically checks and deducts the balance from tenant's wallet.
    4. Submits message to the Jasmin SMPP router.
    5. Saves message record and returns response with message ID.
    """
    # 1. Calculate encoding, segment count and SMPP data coding
    metrics = calculate_sms_metrics(payload.message)
    total_cost = BillingService.calculate_cost(metrics.segments, tenant.cost_per_segment)

    # 2. Atomically deduct balance
    try:
        await BillingService.deduct_balance_atomic(db, tenant.id, total_cost)
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        )

    # 3. Forward to Jasmin SMS Gateway HTTP API
    try:
        jasmin_msgid = await jasmin_client.send_sms(
            sender_id=payload.sender_id,
            recipient=payload.recipient,
            content=payload.message,
            coding=metrics.smpp_coding,
            dlr_url=payload.dlr_callback_url,
        )
    except JasminRouterError as exc:
        # Refund balance since carrier submission failed
        await BillingService.refund_balance_atomic(db, tenant.id, total_cost)
        await db.commit()
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"SMPP Router Error: {exc.message}",
        )

    # 4. Save message in database
    message = SMSMessage(
        tenant_id=tenant.id,
        jasmin_msgid=jasmin_msgid,
        sender_id=payload.sender_id,
        recipient=payload.recipient,
        content=payload.message,
        encoding=metrics.encoding,
        segments=metrics.segments,
        total_cost=total_cost,
        status="SENT",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return SMSResponse(
        id=message.id,
        status=message.status,
        message_id=message.jasmin_msgid,
        encoding=message.encoding,
        segments=message.segments,
        cost=message.total_cost,
        recipient=message.recipient,
        sender_id=message.sender_id,
        created_at=message.created_at,
    )


@router.get("/{message_id}", response_model=SMSDetailResponse)
async def get_message(
    message_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full details and current delivery status for an SMS message."""
    stmt = (
        select(SMSMessage)
        .where(SMSMessage.id == message_id, SMSMessage.tenant_id == tenant.id)
    )
    result = await db.execute(stmt)
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    return SMSDetailResponse(
        id=message.id,
        tenant_id=message.tenant_id,
        message_id=message.jasmin_msgid,
        sender_id=message.sender_id,
        recipient=message.recipient,
        content=message.content,
        encoding=message.encoding,
        segments=message.segments,
        total_cost=message.total_cost,
        status=message.status,
        error_code=message.error_code,
        created_at=message.created_at,
        delivered_at=message.delivered_at,
    )


@router.get("", response_model=SMSListResponse)
async def list_messages(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (QUEUED, SENT, DELIVRD, etc.)"),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lists SMS messages sent by the authenticated tenant."""
    query = select(SMSMessage).where(SMSMessage.tenant_id == tenant.id)
    count_query = select(func.count(SMSMessage.id)).where(SMSMessage.tenant_id == tenant.id)

    if status_filter:
        query = query.where(SMSMessage.status == status_filter.upper())
        count_query = count_query.where(SMSMessage.status == status_filter.upper())

    total_res = await db.execute(count_query)
    total = total_res.scalar_one()

    offset = (page - 1) * limit
    stmt = query.order_by(desc(SMSMessage.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return SMSListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[
            SMSDetailResponse(
                id=m.id,
                tenant_id=m.tenant_id,
                message_id=m.jasmin_msgid,
                sender_id=m.sender_id,
                recipient=m.recipient,
                content=m.content,
                encoding=m.encoding,
                segments=m.segments,
                total_cost=m.total_cost,
                status=m.status,
                error_code=m.error_code,
                created_at=m.created_at,
                delivered_at=m.delivered_at,
            )
            for m in items
        ],
    )
