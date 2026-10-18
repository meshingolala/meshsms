import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.api.deps import get_current_tenant
from meshsms.database import get_db
from meshsms.models.tenant import Tenant
from meshsms.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantTopup,
    TenantUpdate,
)

logger = logging.getLogger("meshsms.api.tenants")

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(get_db),
):
    """Provisions a new tenant with an API key and initial balance."""
    api_key = payload.api_key or f"live_sk_{secrets.token_hex(24)}"

    # Check key uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.api_key == api_key))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this API key already exists",
        )

    tenant = Tenant(
        name=payload.name,
        api_key=api_key,
        balance=payload.initial_balance,
        cost_per_segment=payload.cost_per_segment,
        dlr_webhook_url=payload.dlr_webhook_url,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info("Created tenant %s (%s)", tenant.name, tenant.id)
    return tenant


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant_profile(
    tenant: Tenant = Depends(get_current_tenant),
):
    """Retrieves authenticated tenant's profile, balance, and settings."""
    return tenant


@router.post("/{tenant_id}/topup", response_model=TenantResponse)
async def topup_balance(
    tenant_id: str,
    payload: TenantTopup,
    db: AsyncSession = Depends(get_db),
):
    """Adds credit to a tenant's wallet balance."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.balance = tenant.balance + payload.amount
    await db.commit()
    await db.refresh(tenant)

    logger.info("Topped up tenant %s with %s. New balance: %s", tenant_id, payload.amount, tenant.balance)
    return tenant


@router.patch("/me", response_model=TenantResponse)
async def update_tenant(
    payload: TenantUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Updates the authenticated tenant's settings (e.g. DLR webhook URL, name)."""
    if payload.name is not None:
        tenant.name = payload.name
    if payload.cost_per_segment is not None:
        tenant.cost_per_segment = payload.cost_per_segment
    if payload.dlr_webhook_url is not None:
        tenant.dlr_webhook_url = payload.dlr_webhook_url
    if payload.is_active is not None:
        tenant.is_active = payload.is_active

    await db.commit()
    await db.refresh(tenant)
    return tenant
