# Building an Enterprise SMPP SMS Gateway (Production Architecture)

To handle high-throughput SMS traffic (hundreds or thousands of messages per second) and connect directly to Mobile Network Operators (MNOs) or Tier-1 aggregators, you must use the **SMPP (Short Message Peer-to-Peer)** protocol (typically v3.4 or v5.0).

This guide covers the complete end-to-end architecture, Docker deployment, SMPP routing configuration, and middleware API implementation using **Jasmin SMS Gateway**, **RabbitMQ**, **Redis**, **PostgreSQL**, and **FastAPI**.

---

## 1. System Architecture Overview

```
                                  +-----------------------+
                                  |   PostgreSQL (DB)     |
                                  | Users, Logs, Billing  |
                                  +-----------+-----------+
                                              ^
                                              |
+--------------+     HTTPS/JSON   +-----------+-----------+     HTTP/AMQP     +-----------------------+
| Client Apps  | ---------------> |  API & Billing Layer  | ----------------> |  Jasmin SMS Gateway   |
| (Web/Mobile) | <--------------- |  (FastAPI / Node.js)  | <---------------- |  (SMPP Router Engine) |
+--------------+   DLR Webhooks   +-----------------------+   DLR Callbacks   +-----------+-----------+
                                                                                          |
                                                                          +---------------+---------------+
                                                                          |                               |
                                                                   +------+-------+               +-------+------+
                                                                   |   RabbitMQ   |               |    Redis     |
                                                                   | (Msg Broker) |               | (DLR Lookup) |
                                                                   +--------------+               +--------------+
                                                                          |
                                                                    SMPP v3.4 (TCP)
                                                                          |
                                                                          v
                                                          +-------------------------------+
                                                          | Mobile Network Operator (MNO) |
                                                          |   or Upstream SMPP Carrier    |
                                                          +-------------------------------+
```

### Core Responsibilities:
1. **API & Billing Layer (Your Application):** Handles customer authentication (API keys), rate limiting, credit deduction, sender ID validation, and segment calculation before passing the message to Jasmin.
2. **Jasmin SMS Gateway:** An open-source, high-performance SMPP router written in Python (Twisted). It manages persistent TCP connections (binds) to telecom carriers, handles windowing/throttling, and processes Delivery Receipts (DLRs).
3. **RabbitMQ:** Queues outbound (MT - Mobile Terminated) and inbound (MO - Mobile Originated) messages so spikes in traffic never drop messages.
4. **Redis:** Tracks message IDs temporarily to map asynchronous carrier Delivery Receipts (DLRs) back to the original submission.

---

## 2. Infrastructure Setup (`docker-compose.yml`)

Create a `docker-compose.yml` file to spin up Jasmin, RabbitMQ, Redis, and an SMPP simulator (`smppsim`) so you can test locally before buying a live carrier bind.

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: sms_redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    container_name: sms_rabbitmq
    restart: always
    ports:
      - "5672:5672"
      - "15672:15672" # Management UI (guest/guest)
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

  jasmin:
    image: jookies/jasmin:latest
    container_name: sms_jasmin
    restart: always
    depends_on:
      - redis
      - rabbitmq
    ports:
      - "2775:2775"   # SMPP Server Port (for downstream SMPP clients)
      - "8990:8990"   # JCli Telnet Management Port
      - "1401:1401"   # Jasmin HTTP API Port
    environment:
      - REDIS_CLIENT_HOST=redis
      - REDIS_CLIENT_PORT=6379
      - AMQP_BROKER_HOST=rabbitmq
      - AMQP_BROKER_PORT=5672
      - ENABLE_PUBLISH_SUBMIT_SM_RESP=1
    volumes:
      - ./jasmin_store:/etc/jasmin/store
      - ./jasmin_logs:/var/log/jasmin

  # Optional: SMPP Simulator for testing without a real telecom operator
  smppsim:
    image: meltedice/smppsim:latest
    container_name: sms_smppsim
    ports:
      - "2776:2775" # Simulated Carrier SMPP Port
      - "8088:88"   # Simulator Web UI

volumes:
  redis_data:
  rabbitmq_data:
```

Run the stack:
```bash
docker compose up -d
```

---

## 3. Configuring Jasmin via `jcli` (SMPP Binds & Routing)

Jasmin is configured via its built-in Telnet CLI (`jcli`) on port `8990`. Default credentials are `jcliadmin` / `jclipwd`.

Connect to Jasmin CLI:
```bash
telnet localhost 8990
```

Once inside the `jcli :` prompt, run the following commands to set up your upstream telecom carrier, an internal user for your API, and a default route:

### Step A: Add an Upstream Carrier Connector (SMPP Client)
When a Mobile Network Operator (MNO) gives you an SMPP account, they will provide an IP, Port, `system_id` (username), `password`, and throughput limit (MPS - Messages Per Second).

```text
smppccm -a
> cid carrier_mtn
> host 192.0.2.50
> port 2775
> username my_smpp_system_id
> password my_smpp_password
> bind transceiver
> submit_throughput 50
> dlr_msgid 1
> ok
```
*(Note: If testing with the local `smppsim` container, set `host smppsim`, `port 2775`, `username smppclient1`, `password password`).*

Start the connector:
```text
smppccm -1 carrier_mtn
```

### Step B: Create a Group and Internal API User
Your FastAPI middleware needs credentials to submit messages to Jasmin's HTTP API:

```text
group -a
> gid api_group
> ok

user -a
> uid internal_api
> gid api_group
> username gateway_api_user
> password super_secret_pwd
> ok
```

### Step C: Configure Outbound (MT) Routing
Route all messages (`DefaultRoute`) coming from your internal API through the `carrier_mtn` SMPP connector:

```text
mtrouter -a
> type DefaultRoute
> connector smppc(carrier_mtn)
> rate 0.00
> ok
```

### Step D: Save Configuration to Disk
Always persist changes before exiting:
```text
persist
quit
```

---

## 4. Database Schema (PostgreSQL)

Your middleware layer needs a database to manage tenants, API keys, balances, and message states.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    balance NUMERIC(12, 4) DEFAULT 0.0000,
    cost_per_segment NUMERIC(8, 4) DEFAULT 0.0150,
    dlr_webhook_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sms_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    jasmin_msgid VARCHAR(100) UNIQUE,
    sender_id VARCHAR(15) NOT NULL,
    recipient VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    encoding VARCHAR(10) NOT NULL, -- 'GSM7' or 'UCS2'
    segments INT NOT NULL,
    total_cost NUMERIC(8, 4) NOT NULL,
    status VARCHAR(20) DEFAULT 'QUEUED', -- QUEUED, SENT, DELIVRD, UNDELIV, EXPIRED, REJECTD
    error_code VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP
);

CREATE INDEX idx_jasmin_msgid ON sms_messages(jasmin_msgid);
```

---

## 5. Building the Middleware API & DLR Engine (Python FastAPI)

Your users should **never** talk directly to Jasmin. Instead, they call your FastAPI service, which handles authentication, calculates multipart SMS segments, deducts balance atomically, calls Jasmin (`http://localhost:1401/send`), and listens for Delivery Receipts (DLRs).

### Segment & Encoding Math
In SMPP:
* **GSM-7 (Standard ASCII/Latin):**
  * Single message: $\le 160$ characters ($1$ segment).
  * Multipart message: $> 160$ characters, split into $\lceil \frac{N}{153} \rceil$ segments ($7$ bytes used for UDH - User Data Header).
* **UCS-2 (Unicode/Emojis/Non-Latin):**
  * Single message: $\le 70$ characters ($1$ segment).
  * Multipart message: $> 70$ characters, split into $\lceil \frac{N}{67} \rceil$ segments.

### Complete `main.py` Implementation

```python
import math
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from pydantic import BaseModel, Field

app = FastAPI(title="Enterprise SMPP SMS Gateway API")

JASMIN_SEND_URL = "http://localhost:1401/send"
JASMIN_USER = "gateway_api_user"
JASMIN_PASS = "super_secret_pwd"
PUBLIC_DLR_CALLBACK_URL = "http://host.docker.internal:8000/internal/dlr-webhook"

# Basic GSM 03.38 character set
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = set("^{}\\[~]|€")


def calculate_sms_metrics(text: str):
    """Determines encoding (GSM7 vs UCS2) and exact segment count."""
    is_gsm7 = all(c in GSM7_BASIC or c in GSM7_EXTENDED for c in text)

    if is_gsm7:
        # Extended characters take 2 septets in GSM7
        septet_length = sum(2 if c in GSM7_EXTENDED else 1 for c in text)
        segments = 1 if septet_length <= 160 else math.ceil(septet_length / 153)
        return "GSM7", segments, 0  # coding=0 in SMPP
    else:
        char_length = len(text)
        segments = 1 if char_length <= 70 else math.ceil(char_length / 67)
        return "UCS2", segments, 8  # coding=8 (UCS2) in SMPP


class SendSMSPayload(BaseModel):
    sender_id: str = Field(..., max_length=11, description="Alphanumeric Sender ID (max 11 chars) or Shortcode")
    recipient: str = Field(..., pattern=r"^\+?[1-9]\d{7,14}$", description="E.164 format phone number")
    message: str = Field(..., min_length=1, max_length=1600)


@app.post("/v1/messages")
async def send_sms(payload: SendSMSPayload, x_api_key: str = Header(...)):
    # 1. Authenticate Tenant & Check Balance (Replace with actual PostgreSQL query)
    if x_api_key != "live_sk_test12345":
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # 2. Calculate Encoding and Segments
    encoding, segments, smpp_coding = calculate_sms_metrics(payload.message)

    # 3. Prepare Parameters for Jasmin HTTP API
    jasmin_params = {
        "username": JASMIN_USER,
        "password": JASMIN_PASS,
        "to": payload.recipient.lstrip("+"),
        "from": payload.sender_id,
        "content": payload.message,
        "coding": smpp_coding,
        "dlr": "yes",
        "dlr-url": PUBLIC_DLR_CALLBACK_URL,
        "dlr-level": 2,  # 1: SMSC level, 2: Terminal/Handset level, 3: Both
        "dlr-method": "POST"
    }

    # 4. Forward to Jasmin SMPP Router
    async with httpx.AsyncClient() as client:
        resp = await client.get(JASMIN_SEND_URL, params=jasmin_params)

    # Jasmin returns 'Success "<msgid>"' on 200 OK
    resp_text = resp.text.strip()
    if resp.status_code != 200 or not resp_text.startswith("Success"):
        raise HTTPException(status_code=502, detail=f"SMPP Router Error: {resp_text}")

    jasmin_msgid = resp_text.split('"')[1]

    # 5. Save to PostgreSQL & Deduct Tenant Balance here
    return {
        "status": "QUEUED",
        "message_id": jasmin_msgid,
        "encoding": encoding,
        "segments": segments,
        "recipient": payload.recipient
    }


@app.post("/internal/dlr-webhook")
async def receive_jasmin_dlr(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint called automatically by Jasmin when the telecom carrier returns
    a Delivery Receipt (submit_sm_resp / deliver_sm).
    """
    form_data = await request.form()
    msgid = form_data.get("id")
    message_status = form_data.get("message_status")  # e.g., DELIVRD, UNDELIV, EXPIRED, REJECTD
    err_code = form_data.get("err")
    donedate = form_data.get("donedate")

    # 1. Update message status in PostgreSQL where jasmin_msgid == msgid
    print(f"[DLR RECEIVED] MsgID: {msgid} | Status: {message_status} | Error: {err_code} | Done: {donedate}")

    # 2. Trigger webhook to your customer's application asynchronously
    # background_tasks.add_task(forward_webhook_to_tenant, msgid, message_status, err_code)

    # Jasmin requires an exact body of 'ACK/Jasmin' to mark the DLR as processed
    return "ACK/Jasmin"
```

---

## 6. Key SMPP Operational Concepts

When negotiating and setting up SMPP binds with Mobile Network Operators or Tier-1 aggregators, you will need to configure these parameters:

### 1. TON (Type of Number) and NPI (Numbering Plan Indicator)
SMPP requires numerical flags indicating the format of the `source_addr` (Sender ID) and `dest_addr` (Recipient):
* **Alphanumeric Sender ID (e.g., `"MYBRAND"`):**
  * `source_addr_ton = 5` (Alphanumeric)
  * `source_addr_npi = 0` (Unknown)
* **International Number (e.g., `"23324XXXXXXX"`):**
  * `source_addr_ton = 1` (International)
  * `source_addr_npi = 1` (ISDN/E.164)
* **Shortcode (e.g., `"1448"`):**
  * `source_addr_ton = 3` (Network Specific)
  * `source_addr_npi = 0` or `1`

In Jasmin `jcli`, you can configure this per connector:
```text
smppccm -u carrier_mtn
> src_ton 5
> src_npi 0
> dst_ton 1
> dst_npi 1
> ok
```

### 2. Windowing & Throughput Control (`submit_throughput`)
Carriers enforce strict TPS/MPS (Transactions/Messages Per Second) limits on your SMPP bind (e.g., $50\text{ MPS}$). If your application bursts $2,000$ messages in $1$ second without throttling, the carrier will return SMPP Error `0x00000058` (`ESME_RTHROTTLED`).
* Always set `submit_throughput` in Jasmin slightly below your carrier's contract limit (e.g., set `45` if your limit is `50`). Jasmin and RabbitMQ will automatically queue and pace the excess messages.

### 3. Enquire Link (`enquire_link`)
SMPP relies on long-lived TCP connections. Firewalls or NAT gateways often drop idle TCP connections. Jasmin automatically sends `enquire_link` PDUs every $30\text{ seconds}$ (configurable via `elink_interval`) to keep the carrier session alive and automatically reconnects if the link drops.

---

## 7. Production Deployment Checklist

- [ ] **IP Whitelisting & VPN:** Telecom operators rarely expose SMPP ports to the public internet. Prepare an **IPsec Site-to-Site VPN** (using StrongSwan) or provide a static Elastic IP for carrier firewall whitelisting.
- [ ] **Sender ID Registration:** Pre-register Alphanumeric Sender IDs with local telecom regulators/MNOs to prevent messages from being dropped by carrier firewalls.
- [ ] **DLR Timeout Worker:** Sometimes carriers never return a final DLR if a user's phone is switched off for days. Run a cron job to mark messages stuck in `SENT` for $>72\text{ hours}$ as `EXPIRED`.
- [ ] **Least-Cost / Failover Routing:** Add multiple SMPP connectors in Jasmin and use `FailoverMTroute` so traffic automatically fails over to a backup aggregator if a primary carrier bind goes down.