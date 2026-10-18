import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from meshsms.models.message import SMSMessage
from meshsms.services.expiry_worker import ExpiryWorker


async def test_expiry_worker(db_session):
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(hours=80)
    recent_time = now - timedelta(hours=10)

    # 1. Create a stale sent message (> 72 hours)
    stale_msg = SMSMessage(
        id="msg-stale-001",
        tenant_id="tenant-test-111",
        jasmin_msgid="jasmin-stale-001",
        sender_id="TEST",
        recipient="+12025550100",
        content="Stale message",
        encoding="GSM7",
        segments=1,
        total_cost=0.015,
        status="SENT",
        created_at=stale_time,
    )
    # 2. Create a recent sent message (< 72 hours)
    recent_msg = SMSMessage(
        id="msg-recent-002",
        tenant_id="tenant-test-111",
        jasmin_msgid="jasmin-recent-002",
        sender_id="TEST",
        recipient="+12025550101",
        content="Recent message",
        encoding="GSM7",
        segments=1,
        total_cost=0.015,
        status="SENT",
        created_at=recent_time,
    )
    db_session.add_all([stale_msg, recent_msg])
    await db_session.commit()

    # 3. Run expiry worker with 72h threshold
    expired_count = await ExpiryWorker.expire_stale_messages(db_session, max_age_hours=72)
    assert expired_count == 1

    # 4. Check states
    stale_res = await db_session.execute(select(SMSMessage).where(SMSMessage.id == "msg-stale-001"))
    stale_updated = stale_res.scalar_one()
    assert stale_updated.status == "EXPIRED"
    assert stale_updated.error_code == "TIMEOUT"

    recent_res = await db_session.execute(select(SMSMessage).where(SMSMessage.id == "msg-recent-002"))
    recent_updated = recent_res.scalar_one()
    assert recent_updated.status == "SENT"
    assert recent_updated.error_code is None
