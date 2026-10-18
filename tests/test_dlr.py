import pytest
from sqlalchemy import select
from meshsms.models.message import SMSMessage


async def test_dlr_webhook_success(client, db_session):
    # 1. Send SMS
    send_resp = await client.post(
        "/v1/messages",
        json={
            "sender_id": "MYBRAND",
            "recipient": "+12025550143",
            "message": "Testing DLR flow",
        },
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert send_resp.status_code == 201
    jasmin_msgid = send_resp.json()["message_id"]

    # 2. Receive DLR form data from Jasmin
    dlr_form = {
        "id": jasmin_msgid,
        "message_status": "DELIVRD",
        "err": "000",
        "donedate": "2610181530",
    }
    dlr_resp = await client.post(
        "/internal/dlr-webhook",
        data=dlr_form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert dlr_resp.status_code == 200
    assert dlr_resp.text == "ACK/Jasmin"

    # 3. Verify in database
    stmt = select(SMSMessage).where(SMSMessage.jasmin_msgid == jasmin_msgid)
    result = await db_session.execute(stmt)
    msg = result.scalar_one()
    assert msg.status == "DELIVRD"
    assert msg.delivered_at is not None
    assert msg.error_code is None


async def test_dlr_webhook_undelivered_with_error(client, db_session):
    # 1. Send SMS
    send_resp = await client.post(
        "/v1/messages",
        json={
            "sender_id": "MYBRAND",
            "recipient": "+12025550143",
            "message": "Testing failed delivery",
        },
        headers={"X-API-Key": "live_sk_test12345"},
    )
    jasmin_msgid = send_resp.json()["message_id"]

    # 2. Receive DLR indicating failure (e.g. absent subscriber error code 027)
    dlr_form = {
        "id": jasmin_msgid,
        "message_status": "UNDELIV",
        "err": "027",
        "donedate": "2610181535",
    }
    dlr_resp = await client.post(
        "/internal/dlr-webhook",
        data=dlr_form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert dlr_resp.status_code == 200
    assert dlr_resp.text == "ACK/Jasmin"

    # 3. Verify in database
    stmt = select(SMSMessage).where(SMSMessage.jasmin_msgid == jasmin_msgid)
    result = await db_session.execute(stmt)
    msg = result.scalar_one()
    assert msg.status == "UNDELIV"
    assert msg.error_code == "027"
    assert msg.delivered_at is None
