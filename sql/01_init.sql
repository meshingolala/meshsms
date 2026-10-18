-- MeshSMS PostgreSQL Database Schema
-- Initialize extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants table: multi-tenant authentication, wallet balance, and webhook routing
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    balance NUMERIC(12, 4) DEFAULT 0.0000,
    cost_per_segment NUMERIC(8, 4) DEFAULT 0.0150,
    dlr_webhook_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- SMS Messages table: end-to-end message tracking from queue to carrier delivery
CREATE TABLE IF NOT EXISTS sms_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    jasmin_msgid VARCHAR(100) UNIQUE,
    sender_id VARCHAR(15) NOT NULL,
    recipient VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    encoding VARCHAR(10) NOT NULL, -- 'GSM7' or 'UCS2'
    segments INT NOT NULL,
    total_cost NUMERIC(8, 4) NOT NULL,
    status VARCHAR(20) DEFAULT 'QUEUED', -- QUEUED, SENT, DELIVRD, UNDELIV, EXPIRED, REJECTD, FAILED
    error_code VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP WITH TIME ZONE
);

-- Indices for high-throughput lookup and DLR reconciliation
CREATE INDEX IF NOT EXISTS idx_jasmin_msgid ON sms_messages(jasmin_msgid);
CREATE INDEX IF NOT EXISTS idx_tenant_created ON sms_messages(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_message_status ON sms_messages(status);
CREATE INDEX IF NOT EXISTS idx_message_recipient ON sms_messages(recipient);

-- Seed initial demo tenant
INSERT INTO tenants (id, name, api_key, balance, cost_per_segment, is_active)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'Demo Enterprise Tenant',
    'live_sk_test12345',
    100.0000,
    0.0150,
    TRUE
)
ON CONFLICT (api_key) DO NOTHING;
