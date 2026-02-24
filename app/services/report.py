from datetime import datetime
from app.database.repositories.transaction import TransactionRepository
from app.constants import UZT, CATEGORY_DISPLAY, uzbek_month_year
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("report")


class ReportService:
    """Generates formatted reports from transaction data."""

    def __init__(self, txn_repo: TransactionRepository):
        self.txn_repo = txn_repo

    async def get_balance(self, user_id: int) -> str:
        """Net balance across all currencies."""
        uzs = await self.txn_repo.get_balance(user_id, "UZS")
        usd = await self.txn_repo.get_balance(user_id, "USD")

        has_uzs = uzs["income"] > 0 or uzs["expense"] > 0
        has_usd = usd["income"] > 0 or usd["expense"] > 0

        if not has_uzs and not has_usd:
            return "💰 *Balans*\n\nHali hech qanday operatsiya yo'q."

        lines = ["💰 *Balans*\n"]

        if has_uzs:
            lines.append("🇺🇿 *So'm:*")
            lines.append(f"  📈 Kirim: {format_amount(uzs['income'], 'UZS')}")
            lines.append(f"  📉 Chiqim: {format_amount(uzs['expense'], 'UZS')}")
            balance_emoji = "✅" if uzs["balance"] >= 0 else "🔴"
            lines.append(f"  {balance_emoji} Balans: {format_amount(uzs['balance'], 'UZS')}")

        if has_usd:
            if has_uzs:
                lines.append("")
            lines.append("🇺🇸 *Dollar:*")
            lines.append(f"  📈 Kirim: {format_amount(usd['income'], 'USD')}")
            lines.append(f"  📉 Chiqim: {format_amount(usd['expense'], 'USD')}")
            balance_emoji = "✅" if usd["balance"] >= 0 else "🔴"
            lines.append(f"  {balance_emoji} Balans: {format_amount(usd['balance'], 'USD')}")

        return "\n".join(lines)

    async def get_today_report(self, user_id: int) -> str:
        """Today's transactions summary."""
        transactions = await self.txn_repo.get_today(user_id)
        today_str = datetime.now(UZT).strftime("%d.%m.%Y")

        if not transactions:
            return f"📊 *Bugungi hisobot* ({today_str})\n\nBugun hech qanday operatsiya yo'q."

        lines = [f"📊 *Bugungi hisobot* ({today_str})\n"]
        totals = {"income_uzs": 0, "expense_uzs": 0, "income_usd": 0, "expense_usd": 0}

        for txn in transactions:
            emoji = "📈" if txn.type == "income" else "📉"
            cat = CATEGORY_DISPLAY.get(txn.category, txn.category)
            time_str = txn.created_at.strftime("%H:%M") if txn.created_at else ""
            lines.append(f"{emoji} {format_amount(txn.amount, txn.currency)} | {cat} | {time_str}")

            key = f"{txn.type}_{txn.currency.lower()}"
            if key in totals:
                totals[key] += txn.amount

        lines.append("\n─────────────────")
        if totals["income_uzs"] > 0 or totals["expense_uzs"] > 0:
            lines.append(f"📈 Kirim: {format_amount(totals['income_uzs'], 'UZS')}")
            lines.append(f"📉 Chiqim: {format_amount(totals['expense_uzs'], 'UZS')}")
            net = totals["income_uzs"] - totals["expense_uzs"]
            lines.append(f"{'✅' if net >= 0 else '🔴'} Farq: {format_amount(net, 'UZS')}")
        if totals["income_usd"] > 0 or totals["expense_usd"] > 0:
            lines.append(f"📈 Kirim: {format_amount(totals['income_usd'], 'USD')}")
            lines.append(f"📉 Chiqim: {format_amount(totals['expense_usd'], 'USD')}")

        return "\n".join(lines)

    async def get_month_report(self, user_id: int) -> str:
        """Current month grouped by category."""
        rows = await self.txn_repo.get_month_by_category(user_id)
        now = datetime.now(UZT)

        if not rows:
            return f"📅 *Oylik hisobot* ({uzbek_month_year(now)})\n\nBu oyda hech qanday operatsiya yo'q."

        lines = [f"📅 *Oylik hisobot* ({uzbek_month_year(now)})\n"]

        # Group by type
        income_cats = {}
        expense_cats = {}
        for cat, txn_type, currency, total in rows:
            cat_name = CATEGORY_DISPLAY.get(cat, cat)
            entry = f"{cat_name}: {format_amount(total, currency)}"
            if txn_type == "income":
                income_cats[cat] = entry
            else:
                expense_cats[cat] = entry

        if income_cats:
            lines.append("📈 *Kirimlar:*")
            for entry in income_cats.values():
                lines.append(f"  {entry}")

        if expense_cats:
            if income_cats:
                lines.append("")
            lines.append("📉 *Chiqimlar:*")
            for entry in expense_cats.values():
                lines.append(f"  {entry}")

        return "\n".join(lines)

    async def get_week_report(self, user_id: int) -> str:
        """Last 7 days transactions summary."""
        transactions = await self.txn_repo.get_this_week(user_id)

        if not transactions:
            return "📅 *Haftalik hisobot*\n\nOxirgi 7 kunda hech qanday operatsiya yo'q."

        lines = ["📅 *Haftalik hisobot* (oxirgi 7 kun)\n"]
        totals = {"income_uzs": 0, "expense_uzs": 0, "income_usd": 0, "expense_usd": 0}

        for txn in transactions:
            emoji = "📈" if txn.type == "income" else "📉"
            cat = CATEGORY_DISPLAY.get(txn.category, txn.category)
            date_str = txn.created_at.strftime("%d.%m %H:%M") if txn.created_at else ""
            lines.append(f"{emoji} {format_amount(float(txn.amount), txn.currency)} | {cat} | {date_str}")

            key = f"{txn.type}_{txn.currency.lower()}"
            if key in totals:
                totals[key] += float(txn.amount)

        lines.append("\n─────────────────")
        lines.append(f"📊 Jami operatsiyalar: *{len(transactions)}*")
        if totals["income_uzs"] > 0 or totals["expense_uzs"] > 0:
            lines.append(f"📈 Kirim: {format_amount(totals['income_uzs'], 'UZS')}")
            lines.append(f"📉 Chiqim: {format_amount(totals['expense_uzs'], 'UZS')}")
            net = totals["income_uzs"] - totals["expense_uzs"]
            lines.append(f"{'✅' if net >= 0 else '🔴'} Farq: {format_amount(net, 'UZS')}")
        if totals["income_usd"] > 0 or totals["expense_usd"] > 0:
            lines.append(f"📈 Kirim: {format_amount(totals['income_usd'], 'USD')}")
            lines.append(f"📉 Chiqim: {format_amount(totals['expense_usd'], 'USD')}")

        return "\n".join(lines)

    async def get_full_report(self, user_id: int) -> str:
        """Full report: balance + month summary."""
        balance = await self.get_balance(user_id)
        month = await self.get_month_report(user_id)

        txn_count = await self.txn_repo.count_this_month(user_id)

        lines = [
            "📋 *To'liq hisobot*\n",
            balance,
            "",
            "─────────────────",
            "",
            month,
            "",
            f"📊 Bu oydagi operatsiyalar soni: *{txn_count}*",
        ]
        return "\n".join(lines)
