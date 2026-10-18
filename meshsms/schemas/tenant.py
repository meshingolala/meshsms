from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """Payload to create a new tenant."""
    name: str = Field(..., min_length=2, max_length=100)
    api_key: Optional[str] = Field(None, min_length=16, max_length=64, description="Custom API key or auto-generated")
    initial_balance: Decimal = Field(Decimal("0.0000"), ge=0, description="Initial wallet balance")
    cost_per_segment: Optional[Decimal] = Field(Decimal("0.0150"), gt=0, description="Cost charged per SMS segment")
    dlr_webhook_url: Optional[str] = Field(None, max_length=500, description="Default DLR webhook destination")


class TenantTopup(BaseModel):
    """Payload to add credit to a tenant balance."""
    amount: Decimal = Field(..., gt=0, description="Amount to add to tenant balance")
    reference: Optional[str] = Field(None, description="Optional payment reference / transaction ID")


class TenantResponse(BaseModel):
    """Tenant information response."""
    id: str
    name: str
    api_key: str
    balance: Decimal
    cost_per_segment: Decimal
    dlr_webhook_url: Optional[str]
    is_active: bool
    created_at: datetime


class TenantUpdate(BaseModel):
    """Payload to update tenant configuration."""
    name: Optional[str] = None
    cost_per_segment: Optional[Decimal] = None
    dlr_webhook_url: Optional[str] = None
    is_active: Optional[bool] = None
