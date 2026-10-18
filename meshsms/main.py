import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from meshsms.config import settings
from meshsms.database import init_db
from meshsms.api.v1 import v1_router
from meshsms.api.v1.dlr import router as dlr_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meshsms")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handling."""
    logger.info("Starting MeshSMS Gateway API (Mock mode: %s)...", settings.MOCK_JASMIN)
    await init_db()
    yield
    logger.info("MeshSMS Gateway API shutting down.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="MeshSMS - Enterprise SMPP SMS Gateway",
        description=(
            "High-throughput enterprise SMS gateway middleware interfacing with "
            "Jasmin SMS Gateway, RabbitMQ, and carrier SMPP binds."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Allow CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include internal DLR webhook at root /internal/dlr-webhook
    app.include_router(dlr_router)

    # Include versioned API routes under /v1
    app.include_router(v1_router, prefix=settings.API_PREFIX)

    return app


app = create_app()
