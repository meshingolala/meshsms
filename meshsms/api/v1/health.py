import logging
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.config import settings
from meshsms.database import get_db

logger = logging.getLogger("meshsms.api.health")

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """System health check and dependency status."""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)

    jasmin_ok = False
    jasmin_mode = "mock" if settings.MOCK_JASMIN else "live"
    if settings.MOCK_JASMIN:
        jasmin_ok = True
    else:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(settings.JASMIN_SEND_URL)
                # Jasmin typically responds with 400 Bad Request or similar if no query params provided,
                # which confirms the HTTP server is alive and reachable.
                jasmin_ok = res.status_code in (200, 400, 401, 403, 405)
        except Exception:
            jasmin_ok = False

    status_str = "healthy" if db_ok else "degraded"

    return {
        "status": status_str,
        "database": "connected" if db_ok else "unreachable",
        "jasmin_gateway": {
            "mode": jasmin_mode,
            "send_url": settings.JASMIN_SEND_URL,
            "connected": jasmin_ok,
        },
        "version": "0.1.0",
    }
