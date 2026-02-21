import asyncio
import os
import glob
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

# Temp directory for voice file processing
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")


def _cleanup_temp():
    """Remove orphaned audio files from temp directory on startup."""
    if not os.path.exists(TEMP_DIR):
        return
    removed = 0
    for pattern in ("*.ogg", "*.wav"):
        for f in glob.glob(os.path.join(TEMP_DIR, pattern)):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info(f"Cleaned up {removed} orphaned temp files")


# ── FastAPI app (webhook mode) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for webhook mode."""
    logger.info("Starting application in webhook mode...")
    _cleanup_temp()
    await init_db()

    # Set webhook with explicit allowed updates
    webhook_url = settings.webhook_full_url
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )
    logger.info(f"Webhook set successfully: {webhook_url}")
    yield
    # Don't delete webhook on shutdown — Railway redeploys cause a race
    # condition where the old container deletes it after the new one sets it.
    await bot.session.close()
    logger.info("Application stopped")


app = FastAPI(title="Xisobchi Bot", lifespan=lifespan)

# Allow GitHub Pages (and any origin) to call /stats
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "bot": "Xisobchi"}


@app.get("/stats")
async def stats():
    """Public stats endpoint for the GitHub Pages dashboard.
    Returns only aggregate counts — no personal user data.
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

@app.post(settings.WEBHOOK_PATH)
async def webhook(request: Request):
    # NOTE (Intentional - Finding #2):
    # Telegram webhook secret-token validation (X-Telegram-Bot-Api-Secret-Token header)
    # is intentionally deferred. To harden this endpoint later, pass secret_token=
    # to bot.set_webhook() and validate the header here before processing updates.
    """Receive Telegram updates via webhook."""
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
    _cleanup_temp()
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot is running! Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot session closed")

