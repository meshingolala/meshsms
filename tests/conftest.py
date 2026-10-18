import pytest
from decimal import Decimal
from typing import AsyncGenerator
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from meshsms.config import settings
from meshsms.database import Base, get_db
from meshsms.main import create_app
from meshsms.models.tenant import Tenant
from meshsms.services.jasmin_client import jasmin_client

# Force test settings
settings.MOCK_JASMIN = True

# Test in-memory SQLite database
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Sets up fresh tables for each test and seeds standard test tenant."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed standard test tenant
    async with TestingSessionLocal() as session:
        test_tenant = Tenant(
            id="tenant-test-111",
            name="Test Tenant",
            api_key="live_sk_test12345",
            balance=Decimal("10.0000"),
            cost_per_segment=Decimal("0.0150"),
            dlr_webhook_url="http://testclient.local/webhook",
            is_active=True,
        )
        session.add(test_tenant)

        # Tenant with zero balance for payment required testing
        poor_tenant = Tenant(
            id="tenant-poor-222",
            name="Zero Balance Tenant",
            api_key="live_sk_empty_balance",
            balance=Decimal("0.0000"),
            cost_per_segment=Decimal("0.0150"),
            is_active=True,
        )
        session.add(poor_tenant)

        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    # Ensure mock mode in jasmin client
    jasmin_client.mock_mode = True

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session
