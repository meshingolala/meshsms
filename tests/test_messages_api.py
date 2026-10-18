import pytest
from decimal import Decimal
from sqlalchemy import select
from meshsms.models.tenant import Tenant
from meshsms.models.message import SMSMessage


async def test_send_sms_success(client, db_session):
    payload = {
        "sender_id": "MYBRAND",
        "recipient": "+12025550143",
        "message": "Hello from MeshSMS! Your verification code is 554123.",
    }
    response = await client.post(
        "/v1/messages",
        json=payload,
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "SENT"
    assert data["encoding"] == "GSM7"
    assert data["segments"] == 1
    assert data["cost"] == "0.0150"
    assert data["message_id"].startswith("jasmin_mock_")
    assert data["recipient"] == "+12025550143"
    assert data["sender_id"] == "MYBRAND"

    # Verify balance was deducted: initial 10.0000 - 0.0150 = 9.9850
    stmt = select(Tenant).where(Tenant.api_key == "live_sk_test12345")
    res = await db_session.execute(stmt)
    tenant = res.scalar_one()
    assert tenant.balance == Decimal("9.9850")


async def test_send_sms_unauthorized(client):
    payload = {
        "sender_id": "MYBRAND",
        "recipient": "+12025550143",
        "message": "Unauthorized attempt",
    }
    response = await client.post(
        "/v1/messages",
        json=payload,
        headers={"X-API-Key": "invalid_or_fake_key"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"


async def test_send_sms_insufficient_balance(client):
    payload = {
        "sender_id": "MYBRAND",
        "recipient": "+12025550143",
        "message": "Attempt with zero balance",
    }
    response = await client.post(
        "/v1/messages",
        json=payload,
        headers={"X-API-Key": "live_sk_empty_balance"},
    )
    assert response.status_code == 402
    assert "Insufficient wallet balance" in response.json()["detail"]


async def test_send_sms_validation_error(client):
    # Invalid recipient (missing digits)
    payload = {
        "sender_id": "MYBRAND",
        "recipient": "invalid_phone",
        "message": "Testing validation",
    }
    response = await client.post(
        "/v1/messages",
        json=payload,
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert response.status_code == 422


async def test_get_message_by_id(client):
    # 1. Send message
    payload = {
        "sender_id": "MYBRAND",
        "recipient": "+12025550143",
        "message": "Checking get by ID",
    }
    send_resp = await client.post(
        "/v1/messages",
        json=payload,
        headers={"X-API-Key": "live_sk_test12345"},
    )
    msg_id = send_resp.json()["id"]

    # 2. Query message
    get_resp = await client.get(
        f"/v1/messages/{msg_id}",
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert get_resp.status_code == 200
    msg_data = get_resp.json()
    assert msg_data["id"] == msg_id
    assert msg_data["content"] == "Checking get by ID"
    assert msg_data["status"] == "SENT"


async def test_list_messages(client):
    # Send 2 messages
    for i in range(2):
        await client.post(
            "/v1/messages",
            json={
                "sender_id": "MYBRAND",
                "recipient": f"+1202555014{i}",
                "message": f"Message {i}",
            },
            headers={"X-API-Key": "live_sk_test12345"},
        )

    list_resp = await client.get(
        "/v1/messages?page=1&limit=10",
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
