from datetime import datetime, timezone, timedelta
from app.database.repositories.transaction import TransactionRepository
from app.utils.logger import setup_logger

logger = setup_logger("report")

# Uzbekistan timezone (UTC+5)
UZT = timezone(timedelta(hours=5))

# Category display names in Uzbek
CATEGORY_NAMES = {
    "oziq-ovqat": "🍽 Oziq-ovqat",
    "transport": "🚕 Transport",
    "uy-joy": "🏠 Uy-joy",
    "sog'liq": "💊 Sog'liq",
    "kiyim": "👔 Kiyim",
    "aloqa": "📱 Aloqa",
    "ta'lim": "📚 Ta'lim",
    "ko'ngil ochar": "🎬 Ko'ngil ochar",
    "o'tkazma": "💸 O'tkazma",
    "maosh": "💰 Maosh",
    "boshqa": "📦 Boshqa",
}


def _fmt(amount: float, currency: str) -> str:
    """Format amount with currency."""
    if currency == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.0f} so'm"


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
            lines.append(f"  📈 Kirim: {_fmt(uzs['income'], 'UZS')}")
            lines.append(f"  📉 Chiqim: {_fmt(uzs['expense'], 'UZS')}")
            balance_emoji = "✅" if uzs["balance"] >= 0 else "🔴"
            lines.append(f"  {balance_emoji} Balans: {_fmt(uzs['balance'], 'UZS')}")

        if has_usd:
            if has_uzs:
                lines.append("")
            lines.append("🇺🇸 *Dollar:*")
            lines.append(f"  📈 Kirim: {_fmt(usd['income'], 'USD')}")
            lines.append(f"  📉 Chiqim: {_fmt(usd['expense'], 'USD')}")
            balance_emoji = "✅" if usd["balance"] >= 0 else "🔴"
            lines.append(f"  {balance_emoji} Balans: {_fmt(usd['balance'], 'USD')}")

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
            cat = CATEGORY_NAMES.get(txn.category, txn.category)
            time_str = txn.created_at.strftime("%H:%M") if txn.created_at else ""
            lines.append(f"{emoji} {_fmt(txn.amount, txn.currency)} | {cat} | {time_str}")

            key = f"{txn.type}_{txn.currency.lower()}"
            if key in totals:
                totals[key] += txn.amount

        lines.append("\n─────────────────")
        if totals["income_uzs"] > 0 or totals["expense_uzs"] > 0:
            lines.append(f"📈 Kirim: {_fmt(totals['income_uzs'], 'UZS')}")
            lines.append(f"📉 Chiqim: {_fmt(totals['expense_uzs'], 'UZS')}")
            net = totals["income_uzs"] - totals["expense_uzs"]
            lines.append(f"{'✅' if net >= 0 else '🔴'} Farq: {_fmt(net, 'UZS')}")
        if totals["income_usd"] > 0 or totals["expense_usd"] > 0:
            lines.append(f"📈 Kirim: {_fmt(totals['income_usd'], 'USD')}")
            lines.append(f"📉 Chiqim: {_fmt(totals['expense_usd'], 'USD')}")

        return "\n".join(lines)

    async def get_month_report(self, user_id: int) -> str:
        """Current month grouped by category."""
        rows = await self.txn_repo.get_month_by_category(user_id)
        now = datetime.now(UZT)
        month_str = now.strftime("%B %Y")

        if not rows:
            return f"📅 *Oylik hisobot* ({month_str})\n\nBu oyda hech qanday operatsiya yo'q."

        lines = [f"📅 *Oylik hisobot* ({month_str})\n"]

        # Group by type
        income_cats = {}
        expense_cats = {}
        for cat, txn_type, currency, total in rows:
            cat_name = CATEGORY_NAMES.get(cat, cat)
            entry = f"{cat_name}: {_fmt(total, currency)}"
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

    async def get_full_report(self, user_id: int) -> str:
        """Full report: balance + month summary."""
        balance = await self.get_balance(user_id)
        month = await self.get_month_report(user_id)

        transactions = await self.txn_repo.get_this_month(user_id)
        txn_count = len(transactions)

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
