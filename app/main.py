import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from aiogram.types import Update
from sqlalchemy import select, func
from app.bot import bot, dp
from app.config import settings
from app.database.connection import init_db, async_session
from app.database.models import User, Transaction
from app.utils.logger import setup_logger

logger = setup_logger("main")

# Webhook secret token — prevents fake Telegram updates
_webhook_secret = os.getenv("WEBHOOK_SECRET", secrets.token_hex(32))



# ── FastAPI app (webhook mode) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for webhook mode."""
    logger.info("Starting application in webhook mode...")
    await init_db()

    # Warm up the DB connection pool — init_db() runs Alembic in a subprocess,
    # so the main process has never connected yet.  Without this, the first
    # user request hits a cold serverless Postgres and can time-out / fail.
    try:
        async with async_session() as session:
            await session.execute(select(func.count()).select_from(User))
        logger.info("Database connection pool warmed up ✓")
    except Exception as e:
        logger.warning(f"DB warmup query failed (non-fatal): {e}")

    # Set webhook with explicit allowed updates
    webhook_url = settings.webhook_full_url
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        secret_token=_webhook_secret,
    )
    logger.info(f"Webhook set successfully: {webhook_url}")

    # Start cross-ping keep-alive (pings Koyeb to keep it awake)
    ping_task = None
    if settings.PING_TARGET_URL:
        from app.pinger import ping_loop
        ping_task = asyncio.create_task(ping_loop())
        logger.info(f"Cross-ping started → {settings.PING_TARGET_URL}")

    yield

    # Shutdown
    if ping_task:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
    # Don't delete webhook on shutdown — Railway redeploys cause a race
    # condition where the old container deletes it after the new one sets it.
    await bot.session.close()
    logger.info("Application stopped")


app = FastAPI(title="Xisobchi Bot", lifespan=lifespan)

# CORS: restrict to dashboard origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("DASHBOARD_ORIGIN", "https://xisobchi-dashboard.web.app"),
        "https://xisobchi-dashboard.web.app",
        "https://xisobchi-dashboard.firebaseapp.com",
    ],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "bot": "Xisobchi"}


@app.get("/stats")
async def stats():
    """Public stats endpoint — intentionally unauthenticated.
    Used by the public dashboard. Returns only aggregate counts, no PII.
    To restrict access, add _check_admin(request) guard.
    """
    try:
        async with async_session() as session:
            total_users = (await session.execute(
                select(func.count()).select_from(User)
            )).scalar() or 0

            total_txns = (await session.execute(
                select(func.count()).select_from(Transaction)
            )).scalar() or 0

            total_income = (await session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .where(Transaction.type == "income", Transaction.currency == "UZS")
            )).scalar() or 0

            total_expense = (await session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .where(Transaction.type == "expense", Transaction.currency == "UZS")
            )).scalar() or 0

            # Top 5 categories by transaction count
            cat_rows = (await session.execute(
                select(Transaction.category, func.count().label("cnt"))
                .group_by(Transaction.category)
                .order_by(func.count().desc())
                .limit(5)
            )).all()

        return JSONResponse({
            "total_users": total_users,
            "total_transactions": total_txns,
            "total_income_uzs": float(total_income),
            "total_expense_uzs": float(total_expense),
            "top_categories": [{"name": r.category, "count": r.cnt} for r in cat_rows],
        })
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return JSONResponse({"error": "stats unavailable"}, status_code=500)


# ── Admin helpers ─────────────────────────────────────────────
def _check_admin(request: Request) -> bool:
    """Validate X-Admin-Token header."""
    secret = settings.ADMIN_SECRET
    if not secret:
        return False  # No secret configured = admin disabled
    return request.headers.get("X-Admin-Token") == secret


@app.get("/admin/users")
async def admin_users(request: Request, page: int = 1, limit: int = 20):
    """Paginated list of registered users. Protected by X-Admin-Token."""
    if not _check_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        offset = (page - 1) * limit
        async with async_session() as session:
            total = (await session.execute(
                select(func.count()).select_from(User)
            )).scalar() or 0

            rows = (await session.execute(
                select(User)
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(limit)
            )).scalars().all()

        users = [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "first_name": u.first_name or "",
                "username": u.username or "",
                "created_at": u.created_at.isoformat() if u.created_at else "",
            }
            for u in rows
        ]
        return JSONResponse({"total": total, "page": page, "limit": limit, "users": users})
    except Exception as e:
        logger.error(f"Admin users error: {e}", exc_info=True)
        return JSONResponse({"error": "unavailable"}, status_code=500)


@app.post("/admin/broadcast")
async def admin_broadcast(request: Request):
    """Send a message to all registered users. Protected by X-Admin-Token."""
    if not _check_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    if len(text) > 4096:
        return JSONResponse({"error": "message too long (max 4096 chars)"}, status_code=400)

    try:
        async with async_session() as session:
            rows = (await session.execute(select(User.telegram_id))).scalars().all()

        sent = failed = 0
        for tg_id in rows:
            try:
                await bot.send_message(chat_id=tg_id, text=text, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)  # Throttle: stay under Telegram 30 msg/s limit
            except Exception:
                failed += 1

        logger.info(f"Broadcast: sent={sent} failed={failed}")
        return JSONResponse({"sent": sent, "failed": failed})
    except Exception as e:
        logger.error(f"Broadcast error: {e}", exc_info=True)
        return JSONResponse({"error": "broadcast failed"}, status_code=500)


@app.get("/admin/stats/daily")
async def admin_daily_stats(request: Request):
    """Daily signups for the last 30 days. Protected by X-Admin-Token."""
    if not _check_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        from sqlalchemy import cast, Date as SADate
        async with async_session() as session:
            rows = (await session.execute(
                select(
                    cast(User.created_at, SADate).label("day"),
                    func.count().label("cnt"),
                )
                .group_by(cast(User.created_at, SADate))
                .order_by(cast(User.created_at, SADate))
            )).all()

        return JSONResponse([
            {"day": str(r.day), "count": r.cnt} for r in rows
        ])
    except Exception as e:
        logger.error(f"Daily stats error: {e}", exc_info=True)
        return JSONResponse({"error": "unavailable"}, status_code=500)


@app.delete("/admin/users/{telegram_id}")
async def admin_delete_user(telegram_id: int, request: Request):
    """Hard-delete a user and ALL their transactions. Protected by X-Admin-Token.
    After deletion the user can /start again and will go through onboarding from scratch.
    """
    if not _check_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        async with async_session() as session:
            from app.database.repositories.user import UserRepository
            user_repo = UserRepository(session)
            deleted = await user_repo.delete_by_telegram_id(telegram_id)

        if not deleted:
            return JSONResponse({"error": "User not found"}, status_code=404)

        logger.info(f"Admin hard-deleted user telegram_id={telegram_id} with all their transactions")
        return JSONResponse({"deleted": True, "telegram_id": telegram_id})
    except Exception as e:
        logger.error(f"Admin delete user error: {e}", exc_info=True)
        return JSONResponse({"error": "delete failed"}, status_code=500)


@app.post(settings.WEBHOOK_PATH)
async def webhook(request: Request):
    """Receive Telegram updates via webhook."""
    # Validate Telegram's secret token header
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != _webhook_secret:
        return JSONResponse({"error": "unauthorized"}, status_code=403)
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
    return {"ok": True}


# ── Polling mode (local development) ─────────────────────────
async def start_polling():
    """Start bot in polling mode for local development."""
    logger.info("Starting bot in polling mode...")
    await init_db()

    # Warm up the DB connection pool (same reason as webhook mode)
    try:
        async with async_session() as session:
            await session.execute(select(func.count()).select_from(User))
        logger.info("Database connection pool warmed up ✓")
    except Exception as e:
        logger.warning(f"DB warmup query failed (non-fatal): {e}")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot is running! Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot session closed")

