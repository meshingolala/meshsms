from typing import Annotated
from fastapi import Header, HTTPException, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.database import get_db
from meshsms.models.tenant import Tenant


async def get_current_tenant(
    x_api_key: Annotated[str, Header(..., description="Tenant API Secret Key")],
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Authenticates tenant via X-API-Key header.
    Raises HTTP 401 if invalid or inactive.
    """
    stmt = select(Tenant).where(Tenant.api_key == x_api_key)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is suspended or inactive",
        )

    return tenant
