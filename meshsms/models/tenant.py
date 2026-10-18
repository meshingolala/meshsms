import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, String, Numeric, Boolean, DateTime
from sqlalchemy.orm import relationship

from meshsms.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Tenant(Base):
    """Tenant model for multi-tenant API key authentication and billing."""

    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    balance = Column(Numeric(12, 4), default=Decimal("0.0000"), nullable=False)
    cost_per_segment = Column(Numeric(8, 4), default=Decimal("0.0150"), nullable=False)
    dlr_webhook_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    messages = relationship("SMSMessage", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, balance={self.balance})>"
