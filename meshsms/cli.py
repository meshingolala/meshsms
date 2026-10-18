import argparse
import asyncio
import sys
from decimal import Decimal
import uvicorn
from sqlalchemy import select

from meshsms.config import settings
from meshsms.database import init_db, AsyncSessionLocal
from meshsms.models.tenant import Tenant
from meshsms.services.expiry_worker import ExpiryWorker


async def seed_tenant_command():
    """Seeds a default demo tenant matching the guide requirements."""
    await init_db()
    async with AsyncSessionLocal() as db:
        test_key = "live_sk_test12345"
        stmt = select(Tenant).where(Tenant.api_key == test_key)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            print(f"[Seed] Tenant with key '{test_key}' already exists (ID: {existing.id}, Balance: ${existing.balance:.2f})")
            return

        tenant = Tenant(
            name="Demo Enterprise Tenant",
            api_key=test_key,
            balance=Decimal("100.0000"),
            cost_per_segment=Decimal("0.0150"),
            dlr_webhook_url="http://host.docker.internal:8000/internal/test-client-dlr",
            is_active=True,
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        print(f"[Seed] Successfully seeded tenant: '{tenant.name}'")
        print(f"       Tenant ID: {tenant.id}")
        print(f"       API Key:   {tenant.api_key}")
        print(f"       Balance:   ${tenant.balance:.2f}")
        print(f"       Cost/Seg:  ${tenant.cost_per_segment:.4f}")


async def expire_stale_command(hours: int):
    """Runs the DLR timeout worker."""
    await init_db()
    async with AsyncSessionLocal() as db:
        expired_count = await ExpiryWorker.expire_stale_messages(db, max_age_hours=hours)
        print(f"[Worker] Marked {expired_count} stale message(s) as EXPIRED.")


def run_jasmin_setup():
    """Runs Jasmin telnet configuration script."""
    from scripts.setup_jasmin import configure_jasmin
    configure_jasmin()


def main():
    """CLI Entrypoint for MeshSMS."""
    parser = argparse.ArgumentParser(description="MeshSMS CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Start the MeshSMS API server")
    run_parser.add_argument("--host", default=settings.HOST, help="Host to bind to")
    run_parser.add_argument("--port", type=int, default=settings.PORT, help="Port to listen on")
    run_parser.add_argument("--reload", action="store_true", help="Enable live reload")

    # init-db command
    subparsers.add_parser("init-db", help="Initialize database tables")

    # seed command
    subparsers.add_parser("seed", help="Seed default demo tenant and API key")

    # expire-stale command
    expire_parser = subparsers.add_parser("expire-stale", help="Expire stale sent messages")
    expire_parser.add_argument("--hours", type=int, default=settings.DLR_EXPIRY_HOURS, help="Stale threshold in hours")

    # setup-jasmin command
    subparsers.add_parser("setup-jasmin", help="Automate Jasmin SMPP configuration via Telnet CLI")

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        host = getattr(args, "host", settings.HOST)
        port = getattr(args, "port", settings.PORT)
        reload = getattr(args, "reload", False)
        print(f"Starting MeshSMS API server on {host}:{port}...")
        uvicorn.run("meshsms.main:app", host=host, port=port, reload=reload)
    elif args.command == "init-db":
        asyncio.run(init_db())
        print("Database schema successfully initialized.")
    elif args.command == "seed":
        asyncio.run(seed_tenant_command())
    elif args.command == "expire-stale":
        asyncio.run(expire_stale_command(args.hours))
    elif args.command == "setup-jasmin":
        run_jasmin_setup()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
