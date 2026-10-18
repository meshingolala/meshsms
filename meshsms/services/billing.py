import logging
from decimal import Decimal
from typing import Tuple
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from meshsms.models.tenant import Tenant

logger = logging.getLogger("meshsms.billing")


class InsufficientBalanceError(Exception):
    """Raised when tenant does not have enough balance to send message segments."""
    def __init__(self, required: Decimal, current: Decimal):
        self.required = required
        self.current = current
        super().__init__(
            f"Insufficient wallet balance: Required {required:.4f}, Available {current:.4f}"
        )


class BillingService:
    """Handles tenant balance validation, atomic deductions, and refunds."""

    @staticmethod
    def calculate_cost(segments: int, cost_per_segment: Decimal) -> Decimal:
        """Calculates total cost for the number of segments."""
        return Decimal(segments) * Decimal(cost_per_segment)

    @staticmethod
    async def deduct_balance_atomic(
        db: AsyncSession,
        tenant_id: str,
        cost: Decimal,
    ) -> Decimal:
        """
        Atomically checks and deducts balance in a single transactional query.
        
        Returns the remaining balance after deduction.
        Raises InsufficientBalanceError if balance is insufficient.
        """
        if cost <= Decimal("0.0000"):
            # Zero cost, fetch and return current balance
            stmt = select(Tenant.balance).where(Tenant.id == tenant_id)
            result = await db.execute(stmt)
            curr = result.scalar_one_or_none() or Decimal("0.0000")
            return curr

        # Atomic update with balance check predicate
        stmt = (
            update(Tenant)
            .where(Tenant.id == tenant_id, Tenant.balance >= cost)
            .values(balance=Tenant.balance - cost)
            .returning(Tenant.balance)
        )

        result = await db.execute(stmt)
        new_balance = result.scalar_one_or_none()

        if new_balance is None:
            # Query current balance to return informative error
            bal_stmt = select(Tenant.balance).where(Tenant.id == tenant_id)
            bal_res = await db.execute(bal_stmt)
            current_bal = bal_res.scalar_one_or_none() or Decimal("0.0000")
            logger.warning(
                "Tenant %s failed billing: required=%s, current=%s",
                tenant_id, cost, current_bal
            )
            raise InsufficientBalanceError(required=cost, current=current_bal)

        logger.info(
            "Deducted %s from tenant %s. Remaining balance: %s",
            cost, tenant_id, new_balance
        )
        return new_balance

    @staticmethod
    async def refund_balance_atomic(
        db: AsyncSession,
        tenant_id: str,
        amount: Decimal,
    ) -> Decimal:
        """Atomically refunds an amount back to the tenant wallet."""
        if amount <= Decimal("0.0000"):
            return Decimal("0.0000")

        stmt = (
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(balance=Tenant.balance + amount)
            .returning(Tenant.balance)
        )
        result = await db.execute(stmt)
        new_balance = result.scalar_one_or_none()
        logger.info("Refunded %s to tenant %s. New balance: %s", amount, tenant_id, new_balance)
        return new_balance or Decimal("0.0000")
