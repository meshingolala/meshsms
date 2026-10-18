from decimal import Decimal
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MeshSMS configuration settings."""

    # Application settings
    APP_NAME: str = "MeshSMS"
    DEBUG: bool = False
    API_PREFIX: str = "/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database settings
    # Default to sqlite+aiosqlite for out-of-the-box local usage without external DB;
    # in production set to postgresql+asyncpg://user:pass@host:5432/meshsms
    DATABASE_URL: str = "sqlite+aiosqlite:///./meshsms.db"
    DB_ECHO: bool = False

    # Jasmin SMS Gateway HTTP API settings
    JASMIN_SEND_URL: str = "http://localhost:1401/send"
    JASMIN_USER: str = "gatewayapiuser"
    JASMIN_PASS: str = "supersecretpwd"
    PUBLIC_DLR_CALLBACK_URL: str = "http://host.docker.internal:8000/internal/dlr-webhook"

    # Mock mode: simulates Jasmin HTTP gateway responses for local testing / offline dev
    MOCK_JASMIN: bool = False

    # Jasmin Telnet Management (jcli)
    JASMIN_TELNET_HOST: str = "127.0.0.1"
    JASMIN_TELNET_PORT: int = 8990
    JASMIN_TELNET_USER: str = "jcliadmin"
    JASMIN_TELNET_PASS: str = "jclipwd"

    # Billing defaults
    DEFAULT_COST_PER_SEGMENT: Decimal = Decimal("0.0150")

    # DLR & Expiry configuration
    DLR_EXPIRY_HOURS: int = 72

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
