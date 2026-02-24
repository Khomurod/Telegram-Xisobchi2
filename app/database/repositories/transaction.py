from datetime import datetime, timedelta
from sqlalchemy import select, func, delete as sa_delete
from app.database.models import Transaction
from app.database.repositories.base import BaseRepository
from app.constants import UZT


class TransactionRepository(BaseRepository):
    """Repository for Transaction CRUD and aggregate queries."""

    async def create(
        self,
        user_id: int,
        type: str,
        amount: float,
        currency: str,
        category: str,
        description: str = None,
    ) -> Transaction:
        txn = Transaction(
            user_id=user_id,
            type=type,
            amount=amount,
            currency=currency,
            category=category,
            description=description,
        )
        self.session.add(txn)
        await self.session.commit()
        await self.session.refresh(txn)
        return txn

    async def get_by_user(
        self, user_id: int, start_date: datetime = None, end_date: datetime = None
    ) -> list[Transaction]:
        query = select(Transaction).where(Transaction.user_id == user_id)
        if start_date:
            query = query.where(Transaction.created_at >= start_date)
        if end_date:
            query = query.where(Transaction.created_at <= end_date)
        query = query.order_by(Transaction.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_last(self, user_id: int) -> Transaction | None:
        """Get the most recent transaction for a user."""
        query = (
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete(self, txn_id: int) -> bool:
        """Delete a transaction by ID. Returns True if deleted."""
        stmt = sa_delete(Transaction).where(Transaction.id == txn_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update(self, txn_id: int, **kwargs) -> Transaction | None:
        """Update fields on a transaction. Returns updated object or None."""
        query = select(Transaction).where(Transaction.id == txn_id)
        result = await self.session.execute(query)
        txn = result.scalar_one_or_none()
        if not txn:
            return None
        for key, value in kwargs.items():
            if hasattr(txn, key):
                setattr(txn, key, value)
        await self.session.commit()
        await self.session.refresh(txn)
        return txn

    async def get_by_id(self, txn_id: int) -> Transaction | None:
        """Get a single transaction by its ID."""
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == txn_id)
        )
        return result.scalar_one_or_none()

    async def get_balance(self, user_id: int, currency: str = None) -> dict:
        """Get total income, expense, and net balance."""
        income_q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income"
        )
        expense_q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense"
        )
        if currency:
            income_q = income_q.where(Transaction.currency == currency)
            expense_q = expense_q.where(Transaction.currency == currency)

        income = (await self.session.execute(income_q)).scalar() or 0
        expense = (await self.session.execute(expense_q)).scalar() or 0
        return {"income": income, "expense": expense, "balance": income - expense}

    async def get_today(self, user_id: int) -> list[Transaction]:
        today_start = datetime.now(UZT).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.get_by_user(user_id, start_date=today_start)

    async def get_this_week(self, user_id: int) -> list[Transaction]:
        """Get transactions from the last 7 days."""
        week_start = datetime.now(UZT) - timedelta(days=7)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.get_by_user(user_id, start_date=week_start)

    async def get_this_month(self, user_id: int) -> list[Transaction]:
        month_start = datetime.now(UZT).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self.get_by_user(user_id, start_date=month_start)

    async def get_month_by_category(self, user_id: int) -> list:
        """Get current month totals grouped by category, type, currency."""
        month_start = datetime.now(UZT).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query = (
            select(
                Transaction.category,
                Transaction.type,
                Transaction.currency,
                func.sum(Transaction.amount).label("total"),
            )
            .where(Transaction.user_id == user_id, Transaction.created_at >= month_start)
            .group_by(Transaction.category, Transaction.type, Transaction.currency)
        )
        result = await self.session.execute(query)
        return result.all()

    async def count_this_month(self, user_id: int) -> int:
        """Count transactions this month (cheaper than loading all rows)."""
        month_start = datetime.now(UZT).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count()).select_from(Transaction)
            .where(Transaction.user_id == user_id, Transaction.created_at >= month_start)
        )
        return result.scalar() or 0
