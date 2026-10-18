import logging
from typing import Optional
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.database import get_db
from meshsms.services.dlr_service import DLRService, JASMIN_ACK_RESPONSE
from meshsms.schemas.sms import TenantWebhookNotification

logger = logging.getLogger("meshsms.api.dlr")

router = APIRouter(tags=["DLR"])


@router.post("/internal/dlr-webhook", response_class=PlainTextResponse)
async def receive_jasmin_dlr(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint called automatically by Jasmin SMS Gateway when telecom carrier
    returns a Delivery Receipt (submit_sm_resp / deliver_sm).
    
    Jasmin transmits DLR fields via application/x-www-form-urlencoded:
    - id: Jasmin message ID
    - message_status: DELIVRD, UNDELIV, EXPIRED, REJECTD, etc.
    - err: Carrier SMPP error code (e.g. '000')
    - donedate: Delivery timestamp from SMSC
    
    Jasmin requires an exact response body of 'ACK/Jasmin' to mark receipt as acknowledged.
    """
    content_type = request.headers.get("content-type", "")

    msgid = None
    message_status = None
    err_code = None
    donedate = None

    if "application/json" in content_type:
        try:
            body = await request.json()
            msgid = body.get("id") or body.get("message_id")
            message_status = body.get("message_status") or body.get("status")
            err_code = body.get("err") or body.get("error_code")
            donedate = body.get("donedate")
        except Exception:
            pass
    else:
        # Default application/x-www-form-urlencoded from Jasmin
        try:
            form = await request.form()
            msgid = form.get("id")
            message_status = form.get("message_status")
            err_code = form.get("err")
            donedate = form.get("donedate")
        except Exception:
            # Fallback to query params if any
            params = request.query_params
            msgid = params.get("id")
            message_status = params.get("message_status")
            err_code = params.get("err")
            donedate = params.get("donedate")

    if not msgid:
        logger.warning("DLR webhook called without message id: %s", await request.body())
        return PlainTextResponse(content=JASMIN_ACK_RESPONSE, status_code=200)

    # 1. Update message in DB
    updated_msg = await DLRService.process_dlr(
        db=db,
        jasmin_msgid=str(msgid),
        message_status=str(message_status) if message_status else "DELIVRD",
        error_code=str(err_code) if err_code else None,
        done_date=str(donedate) if donedate else None,
    )

    # 2. Asynchronously notify tenant webhook if configured
    if updated_msg and updated_msg.tenant and updated_msg.tenant.dlr_webhook_url:
        notification = TenantWebhookNotification(
            message_id=updated_msg.id,
            jasmin_msgid=updated_msg.jasmin_msgid,
            recipient=updated_msg.recipient,
            sender_id=updated_msg.sender_id,
            status=updated_msg.status,
            error_code=updated_msg.error_code,
            delivered_at=updated_msg.delivered_at,
        )
        background_tasks.add_task(
            DLRService.dispatch_tenant_webhook,
            updated_msg.tenant.dlr_webhook_url,
            notification,
        )

    # 3. Jasmin mandates exact 'ACK/Jasmin' response body
    return PlainTextResponse(content=JASMIN_ACK_RESPONSE, status_code=200)
