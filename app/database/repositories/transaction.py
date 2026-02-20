from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from app.database.models import Transaction
from app.database.repositories.base import BaseRepository

# Uzbekistan timezone
UZT = timezone(timedelta(hours=5))


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
