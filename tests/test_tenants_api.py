import pytest
from decimal import Decimal


async def test_create_tenant(client):
    payload = {
        "name": "New Fintech Client",
        "initial_balance": "50.0000",
        "cost_per_segment": "0.0120",
        "dlr_webhook_url": "https://fintech.example.com/dlr",
    }
    resp = await client.post("/v1/tenants", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Fintech Client"
    assert data["balance"] == "50.0000"
    assert data["cost_per_segment"] == "0.0120"
    assert data["api_key"].startswith("live_sk_")


async def test_get_current_tenant_profile(client):
    resp = await client.get("/v1/tenants/me", headers={"X-API-Key": "live_sk_test12345"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Tenant"
    assert data["api_key"] == "live_sk_test12345"


async def test_topup_balance(client):
    topup_payload = {"amount": "25.5000"}
    resp = await client.post(
        "/v1/tenants/tenant-test-111/topup",
        json=topup_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    # Initial was 10.0000 + 25.5000 = 35.5000
    assert Decimal(data["balance"]) == Decimal("35.5000")


async def test_update_tenant(client):
    update_payload = {
        "dlr_webhook_url": "https://updated.example.com/callback",
    }
    resp = await client.patch(
        "/v1/tenants/me",
        json=update_payload,
        headers={"X-API-Key": "live_sk_test12345"},
    )
    assert resp.status_code == 200
    assert resp.json()["dlr_webhook_url"] == "https://updated.example.com/callback"
