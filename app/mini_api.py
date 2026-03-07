"""
Mini App API — FastAPI router for the Telegram Mini App.

All endpoints validate Telegram initData from the Authorization header.
Reuses existing repository layer — no new database models needed.
"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.utils.telegram_auth import validate_init_data
from app.utils.logger import setup_logger
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES, UZT

logger = setup_logger("mini_api")

router = APIRouter(prefix="/api/mini", tags=["mini-app"])

# Allow skipping auth in local dev (set DEV_MODE=1 in .env)
_DEV_MODE = os.getenv("DEV_MODE", "") == "1"


async def _get_tg_user(request: Request) -> dict | None:
    """Extract and validate Telegram user from Authorization header."""
    if _DEV_MODE:
        # In dev mode return a mock user for browser testing
        return {"id": 0, "first_name": "DevUser", "username": "dev"}

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tg "):
        return None
    init_data = auth[3:]
    return validate_init_data(init_data, settings.BOT_TOKEN)


# ── GET /api/mini/dashboard ──────────────────────────────────

@router.get("/dashboard")
async def mini_dashboard(request: Request):
    """Balance + recent transactions + monthly category breakdown."""
    tg_user = await _get_tg_user(request)
    if tg_user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    telegram_id = tg_user["id"]

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                return JSONResponse({
                    "user": {"first_name": tg_user.get("first_name", ""), "is_new": True},
                    "balance": {"uzs": {"income": 0, "expense": 0, "balance": 0},
                                "usd": {"income": 0, "expense": 0, "balance": 0}},
                    "recent": [],
                    "categories": [],
                })

            txn_repo = TransactionRepository(session)

            # Balance
            uzs = await txn_repo.get_balance(user.id, "UZS")
            usd = await txn_repo.get_balance(user.id, "USD")

            # Recent transactions (today, max 10)
            today_txns = await txn_repo.get_today(user.id)
            recent = [
                {
                    "id": t.id,
                    "type": t.type,
                    "amount": float(t.amount),
                    "currency": t.currency,
                    "category": t.category,
                    "category_emoji": CATEGORY_EMOJI.get(t.category, "📦"),
                    "category_name": CATEGORY_NAMES.get(t.category, t.category),
                    "description": t.description or "",
                    "created_at": t.created_at.astimezone(UZT).strftime("%H:%M") if t.created_at else "",
                }
                for t in today_txns[:10]
            ]

            # Monthly category breakdown
            cat_rows = await txn_repo.get_month_by_category(user.id)
            categories = [
                {
                    "category": cat,
                    "category_emoji": CATEGORY_EMOJI.get(cat, "📦"),
                    "category_name": CATEGORY_NAMES.get(cat, cat),
                    "type": txn_type,
                    "currency": currency,
                    "total": float(total),
                }
                for cat, txn_type, currency, total in cat_rows
            ]

        return JSONResponse({
            "user": {
                "first_name": user.first_name or tg_user.get("first_name", ""),
                "is_new": False,
            },
            "balance": {
                "uzs": {"income": float(uzs["income"]), "expense": float(uzs["expense"]), "balance": float(uzs["balance"])},
                "usd": {"income": float(usd["income"]), "expense": float(usd["expense"]), "balance": float(usd["balance"])},
            },
            "recent": recent,
            "categories": categories,
        })
    except Exception as e:
        logger.error(f"Mini dashboard error: {e}", exc_info=True)
        return JSONResponse({"error": "unavailable"}, status_code=500)


# ── GET /api/mini/transactions ───────────────────────────────

@router.get("/transactions")
async def mini_transactions(request: Request, page: int = 1, limit: int = 20, type: str = None):
    """Paginated transaction list with optional type filter."""
    tg_user = await _get_tg_user(request)
    if tg_user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    telegram_id = tg_user["id"]

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                return JSONResponse({"transactions": [], "total": 0, "page": page})

            txn_repo = TransactionRepository(session)
            all_txns = await txn_repo.get_by_user(user.id)

            # Optional type filter
            if type in ("income", "expense"):
                all_txns = [t for t in all_txns if t.type == type]

            total = len(all_txns)
            offset = (page - 1) * limit
            page_txns = all_txns[offset:offset + limit]

            transactions = [
                {
                    "id": t.id,
                    "type": t.type,
                    "amount": float(t.amount),
                    "currency": t.currency,
                    "category": t.category,
                    "category_emoji": CATEGORY_EMOJI.get(t.category, "📦"),
                    "category_name": CATEGORY_NAMES.get(t.category, t.category),
                    "description": t.description or "",
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                    "created_at_display": t.created_at.astimezone(UZT).strftime("%d.%m %H:%M") if t.created_at else "",
                }
                for t in page_txns
            ]

        return JSONResponse({
            "transactions": transactions,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if limit > 0 else 0,
        })
    except Exception as e:
        logger.error(f"Mini transactions error: {e}", exc_info=True)
        return JSONResponse({"error": "unavailable"}, status_code=500)


# ── POST /api/mini/transactions ──────────────────────────────

@router.post("/transactions")
async def mini_add_transaction(request: Request):
    """Create a new transaction from the mini app form."""
    tg_user = await _get_tg_user(request)
    if tg_user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    telegram_id = tg_user["id"]

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    txn_type = body.get("type", "").strip()
    amount = body.get("amount")
    currency = body.get("currency", "UZS").strip().upper()
    category = body.get("category", "boshqa").strip()
    description = (body.get("description") or "").strip()

    # Validation
    if txn_type not in ("income", "expense"):
        return JSONResponse({"error": "type must be 'income' or 'expense'"}, status_code=400)
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return JSONResponse({"error": "amount must be a positive number"}, status_code=400)
    if currency not in ("UZS", "USD"):
        return JSONResponse({"error": "currency must be UZS or USD"}, status_code=400)
    if category not in CATEGORY_NAMES:
        category = "boshqa"
    if len(description) > 500:
        description = description[:500]

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(
                telegram_id,
                first_name=tg_user.get("first_name"),
                username=tg_user.get("username"),
            )

            txn_repo = TransactionRepository(session)
            txn = await txn_repo.create(
                user_id=user.id,
                type=txn_type,
                amount=amount,
                currency=currency,
                category=category,
                description=description or None,
            )

        logger.info(f"Mini app: txn #{txn.id} {txn_type} {amount} {currency} [{category}] for tg_id={telegram_id}")

        return JSONResponse({
            "success": True,
            "transaction": {
                "id": txn.id,
                "type": txn_type,
                "amount": amount,
                "currency": currency,
                "category": category,
                "category_emoji": CATEGORY_EMOJI.get(category, "📦"),
            },
        })
    except Exception as e:
        logger.error(f"Mini add transaction error: {e}", exc_info=True)
        return JSONResponse({"error": "save failed"}, status_code=500)


# ── DELETE /api/mini/transactions/{txn_id} ───────────────────

@router.delete("/transactions/{txn_id}")
async def mini_delete_transaction(txn_id: int, request: Request):
    """Delete a transaction (with ownership check)."""
    tg_user = await _get_tg_user(request)
    if tg_user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    telegram_id = tg_user["id"]

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                return JSONResponse({"error": "user not found"}, status_code=404)

            txn_repo = TransactionRepository(session)
            txn = await txn_repo.get_by_id(txn_id)

            if not txn:
                return JSONResponse({"error": "transaction not found"}, status_code=404)

            # Ownership check — only delete your own transactions
            if txn.user_id != user.id:
                return JSONResponse({"error": "forbidden"}, status_code=403)

            await txn_repo.delete(txn_id)

        logger.info(f"Mini app: deleted txn #{txn_id} for tg_id={telegram_id}")
        return JSONResponse({"deleted": True, "id": txn_id})
    except Exception as e:
        logger.error(f"Mini delete transaction error: {e}", exc_info=True)
        return JSONResponse({"error": "delete failed"}, status_code=500)


# ── GET /api/mini/reports ────────────────────────────────────

@router.get("/reports")
async def mini_reports(request: Request):
    """
    Report data for the Reports screen.

    Returns:
    - week:  totals (income/expense) for the last 7 days
    - month: totals + category breakdown for current month
    - daily: per-day income/expense for the last 7 days (for bar chart)
    """
    from datetime import datetime, timedelta

    tg_user = await _get_tg_user(request)
    if tg_user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    telegram_id = tg_user["id"]

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                return JSONResponse({
                    "week": {"income_uzs": 0, "expense_uzs": 0, "income_usd": 0, "expense_usd": 0},
                    "month": {"income_uzs": 0, "expense_uzs": 0, "income_usd": 0, "expense_usd": 0,
                              "count": 0, "categories": []},
                    "daily": [],
                })

            txn_repo = TransactionRepository(session)

            # ── Week totals (last 7 days) ───────────────────
            week_txns = await txn_repo.get_this_week(user.id)
            week = {"income_uzs": 0.0, "expense_uzs": 0.0, "income_usd": 0.0, "expense_usd": 0.0}
            for t in week_txns:
                key = f"{t.type}_{t.currency.lower()}"
                if key in week:
                    week[key] += float(t.amount)

            # ── Month totals + category breakdown ───────────
            month_txns = await txn_repo.get_this_month(user.id)
            month = {"income_uzs": 0.0, "expense_uzs": 0.0, "income_usd": 0.0, "expense_usd": 0.0}
            for t in month_txns:
                key = f"{t.type}_{t.currency.lower()}"
                if key in month:
                    month[key] += float(t.amount)

            cat_rows = await txn_repo.get_month_by_category(user.id)
            month_count = await txn_repo.count_this_month(user.id)
            categories = [
                {
                    "category": cat,
                    "category_emoji": CATEGORY_EMOJI.get(cat, "📦"),
                    "category_name": CATEGORY_NAMES.get(cat, cat),
                    "type": txn_type,
                    "currency": currency,
                    "total": float(total),
                }
                for cat, txn_type, currency, total in cat_rows
            ]
            month["count"] = month_count
            month["categories"] = categories

            # ── Daily breakdown for last 7 days ─────────────
            now = datetime.now(UZT)
            daily = []
            for i in range(6, -1, -1):
                day = now - timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
                day_txns = [
                    t for t in week_txns
                    if t.created_at and day_start <= t.created_at.astimezone(UZT) <= day_end
                ]
                income_uzs = sum(float(t.amount) for t in day_txns if t.type == "income" and t.currency == "UZS")
                expense_uzs = sum(float(t.amount) for t in day_txns if t.type == "expense" and t.currency == "UZS")
                daily.append({
                    "date": day.strftime("%d.%m"),
                    "weekday": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"][day.weekday()],
                    "income_uzs": income_uzs,
                    "expense_uzs": expense_uzs,
                })

        return JSONResponse({
            "week": week,
            "month": month,
            "daily": daily,
        })
    except Exception as e:
        logger.error(f"Mini reports error: {e}", exc_info=True)
        return JSONResponse({"error": "unavailable"}, status_code=500)
