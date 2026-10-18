"""Seed demo tenant and initial balances for MeshSMS."""

import asyncio
from meshsms.cli import seed_tenant_command


if __name__ == "__main__":
    asyncio.run(seed_tenant_command())
