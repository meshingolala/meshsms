# MeshSMS - Enterprise SMPP SMS Gateway

**MeshSMS** is a high-throughput, enterprise-grade SMS Gateway and middleware platform built for connecting modern applications with Mobile Network Operators (MNOs) and Tier-1 aggregators via SMPP v3.4/v5.0 and Jasmin SMS Gateway.

---

## Architecture Overview

```
                                  +-----------------------+
                                  |   PostgreSQL / DB     |
                                  | Tenants, Logs, Billing|
                                  +-----------+-----------+
                                              ^
                                              |
+--------------+     HTTPS/JSON   +-----------+-----------+     HTTP/AMQP     +-----------------------+
| Client Apps  | ---------------> |  MeshSMS API & Billing| ----------------> |  Jasmin SMS Gateway   |
| (Web/Mobile) | <--------------- |   (FastAPI Engine)    | <---------------- |  (SMPP Router Engine) |
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

### Core Features

1. **Intelligent Encoding & Segmentation:**
   - **GSM-7 (Standard Latin):** Single part up to 160 characters (1 segment); multipart split into 153-character chunks with 7-byte UDH headers. Automatically supports GSM 03.38 basic and extended character sets (counting extended characters as 2 septets).
   - **UCS-2 (Unicode/Emoji/Non-Latin):** Single part up to 70 characters (1 segment); multipart split into 67-character chunks.
2. **Atomic Billing & Tenant Management:**
   - Multi-tenant architecture with API key authentication (`X-API-Key`).
   - Real-time balance verification and atomic deduction per calculated message segment.
   - Dynamic tenant top-up and configurable cost-per-segment.
3. **Automated Jasmin SMPP Engine Configuration:**
   - Telnet `jcli` automation script to configure carrier connectors, groups, API users, and outbound MT routing.
   - TON (Type of Number) and NPI (Numbering Plan Indicator) detection for Alphanumeric, International, and Shortcode sender IDs.
   - Configurable message throughput pacing (`submit_throughput`) to respect carrier SLA window limits.
4. **Reliable DLR (Delivery Receipt) Engine:**
   - Webhook callback listener (`/internal/dlr-webhook`) fulfilling carrier ACK protocol with exact `ACK/Jasmin` response.
   - Automatic database status synchronization (`QUEUED`, `SENT`, `DELIVRD`, `UNDELIV`, `EXPIRED`, `REJECTD`).
   - Asynchronous fan-out webhooks to client callback URLs.
5. **DLR Timeout / Expiry Worker:**
   - Sweeps and transitions stale messages stuck in `SENT` without terminal carrier receipts to `EXPIRED`.
6. **Local Carrier Simulator Mode:**
   - Works seamlessly with Docker `smppsim` or built-in mock Jasmin engine for end-to-end local development and CI testing.

---

## Quickstart

### 1. Local Environment Setup

MeshSMS uses Python 3.11+ and `uv`:

```bash
# Create and activate virtual environment
uv venv
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate # Linux/macOS

# Install dependencies in editable mode
uv pip install -e ".[dev]"
```

### 2. Configuration (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key environment settings:
- `DATABASE_URL`: `sqlite+aiosqlite:///./meshsms.db` (local dev) or `postgresql+asyncpg://meshsms:secret@localhost:5432/meshsms` (production)
- `JASMIN_SEND_URL`: URL to Jasmin HTTP API (e.g. `http://localhost:1401/send`)
- `JASMIN_USER`: Jasmin HTTP API user (e.g. `gateway_api_user`)
- `JASMIN_PASS`: Jasmin HTTP API password (e.g. `super_secret_pwd`)
- `PUBLIC_DLR_CALLBACK_URL`: Public or internal callback URL for Jasmin DLR webhooks
- `MOCK_JASMIN`: Set to `true` to run against simulated Jasmin engine without external services.

### 3. Initialize Database & Seed Tenant

```bash
# Seed initial test tenant
python -m meshsms.cli seed
```

This creates a default tenant:
- **Tenant:** Demo Enterprise
- **API Key:** `live_sk_test12345`
- **Initial Balance:** $100.00
- **Cost / Segment:** $0.0150

### 4. Run the API Server

```bash
python -m meshsms.cli run --port 8000
```

Access the OpenAPI documentation at: `http://localhost:8000/docs`.

---

## Docker Deployment (Full Stack)

Launch the full stack including Redis, RabbitMQ, Jasmin Gateway, PostgreSQL, and the SMPP Carrier Simulator:

```bash
docker compose up -d
```

### Automatic Jasmin SMPP Configuration
Run the automated Telnet `jcli` configuration:

```bash
python scripts/setup_jasmin.py
```

---

## API Endpoints

### 1. Send SMS (`POST /v1/messages`)
- **Headers:** `X-API-Key: live_sk_test12345`
- **Body:**
```json
{
  "sender_id": "MESHNEWS",
  "recipient": "+12025550143",
  "message": "Hello from MeshSMS! Your verification code is 849201."
}
```
- **Response:**
```json
{
  "id": "c138f28d-d6ae-4a25-a4b5-bf677f52554e",
  "status": "QUEUED",
  "message_id": "b3e0c079-05eb-4ceb-8d74-9f5aa7c5dece",
  "encoding": "GSM7",
  "segments": 1,
  "cost": 0.015,
  "recipient": "+12025550143",
  "created_at": "2026-10-18T15:30:00Z"
}
```

### 2. Message Lookup (`GET /v1/messages/{id}`)
Fetch message status, segments, and delivery timestamps.

### 3. DLR Webhook (`POST /internal/dlr-webhook`)
Internal endpoint called by Jasmin SMS Gateway with Delivery Receipts. Returns `ACK/Jasmin`.

### 4. Tenant Management (`/v1/tenants`)
- `POST /v1/tenants`: Create a new tenant with API key and rate settings.
- `GET /v1/tenants/me`: View authenticated tenant details, remaining balance, and usage.
- `POST /v1/tenants/{id}/topup`: Add balance to a tenant.

---

## Running Tests

Run the comprehensive test suite:

```bash
pytest
```
