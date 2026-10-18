from fastapi import APIRouter
from meshsms.api.v1.messages import router as messages_router
from meshsms.api.v1.tenants import router as tenants_router
from meshsms.api.v1.health import router as health_router

v1_router = APIRouter()
v1_router.include_router(messages_router)
v1_router.include_router(tenants_router)
v1_router.include_router(health_router)

__all__ = ["v1_router"]
