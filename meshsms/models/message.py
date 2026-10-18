import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, String, Numeric, Integer, Text, DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import relationship

from meshsms.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class SMSMessage(Base):
    """SMS Message model tracking lifecycle from queue to carrier delivery."""

    __tablename__ = "sms_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    jasmin_msgid = Column(String(100), unique=True, nullable=True, index=True)
    sender_id = Column(String(15), nullable=False)
    recipient = Column(String(20), nullable=False, index=True)
    content = Column(Text, nullable=False)
    encoding = Column(String(10), nullable=False)  # 'GSM7' or 'UCS2'
    segments = Column(Integer, nullable=False, default=1)
    total_cost = Column(Numeric(8, 4), nullable=False, default=Decimal("0.0000"))
    status = Column(String(20), default="QUEUED", nullable=False, index=True)
    # Statuses: QUEUED, SENT, DELIVRD, UNDELIV, EXPIRED, REJECTD, FAILED
    error_code = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="messages")

    __table_args__ = (
        Index("idx_jasmin_msgid", "jasmin_msgid"),
        Index("idx_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SMSMessage(id={self.id}, recipient={self.recipient}, status={self.status})>"
