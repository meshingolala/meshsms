"""
Carrier & DLR End-to-End Simulation Script for MeshSMS.

Demonstrates:
1. Submitting an SMS via MeshSMS REST API
2. Simulating carrier SMSC receiving and delivering the message
3. Firing the DLR callback back to /internal/dlr-webhook
4. Verifying the message status updates to DELIVRD
"""

import sys
import time
import httpx

API_BASE = "http://localhost:8000"
API_KEY = "live_sk_test12345"


def main():
    print("=" * 60)
    print(" MeshSMS End-to-End Delivery Simulation")
    print("=" * 60)

    # 1. Send SMS
    payload = {
        "sender_id": "MESHNEWS",
        "recipient": "+12025550143",
        "message": "Welcome to MeshSMS! Your enterprise OTP is 739210.",
    }

    print(f"\n1. Submitting SMS to {API_BASE}/v1/messages...")
    try:
        resp = httpx.post(
            f"{API_BASE}/v1/messages",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        print(f"Error connecting to MeshSMS API: {exc}")
        print("Please ensure the MeshSMS API server is running (e.g. 'python -m meshsms.cli run')")
        sys.exit(1)

    if resp.status_code != 201:
        print(f"Failed to send SMS (HTTP {resp.status_code}): {resp.text}")
        sys.exit(1)

    data = resp.json()
    msg_id = data["id"]
    jasmin_msgid = data["message_id"]
    print(f"   [SUCCESS] Message submitted:")
    print(f"   - Database ID:  {msg_id}")
    print(f"   - Jasmin MsgID: {jasmin_msgid}")
    print(f"   - Encoding:     {data['encoding']}")
    print(f"   - Segments:     {data['segments']}")
    print(f"   - Cost:         ${data['cost']}")

    # 2. Simulate Carrier Delivery Receipt
    print(f"\n2. Simulating Carrier Delivery Receipt for msgid={jasmin_msgid}...")
    dlr_form = {
        "id": jasmin_msgid,
        "message_status": "DELIVRD",
        "err": "000",
        "donedate": time.strftime("%y%m%d%H%M"),
    }

    dlr_resp = httpx.post(
        f"{API_BASE}/internal/dlr-webhook",
        data=dlr_form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5.0,
    )
    print(f"   - DLR Webhook Response: {dlr_resp.status_code} | Body: '{dlr_resp.text}'")
    assert dlr_resp.text == "ACK/Jasmin", "Jasmin requires exact 'ACK/Jasmin' response body!"

    # 3. Verify status in database via API
    print(f"\n3. Verifying updated message state via GET /v1/messages/{msg_id}...")
    check_resp = httpx.get(
        f"{API_BASE}/v1/messages/{msg_id}",
        headers={"X-API-Key": API_KEY},
        timeout=5.0,
    )
    msg_details = check_resp.json()
    print(f"   - Status:       {msg_details['status']}")
    print(f"   - Delivered At: {msg_details['delivered_at']}")
    print(f"   - Error Code:   {msg_details['error_code']}")

    if msg_details["status"] == "DELIVRD":
        print("\n [OK] End-to-end SMS transmission and carrier DLR lifecycle verified!")
    else:
        print(f"\n [FAIL] Expected DELIVRD status, got: {msg_details['status']}")


if __name__ == "__main__":
    main()
