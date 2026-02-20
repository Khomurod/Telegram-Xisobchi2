import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram.types import Update
from app.bot import bot, dp
from app.config import settings
from app.database.connection import init_db
from app.utils.logger import setup_logger

logger = setup_logger("main")


# ── FastAPI app (webhook mode) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for webhook mode."""
    logger.info("Starting application in webhook mode...")
    await init_db()
    await bot.set_webhook(settings.webhook_full_url)
    logger.info(f"Webhook set: {settings.webhook_full_url}")
    yield
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Application stopped")


app = FastAPI(title="Xisobchi Bot", lifespan=lifespan)


@app.post(settings.WEBHOOK_PATH)
async def webhook(request: Request):
    """Receive Telegram updates via webhook."""
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


# ── Polling mode (local development) ─────────────────────────
async def start_polling():
    """Start bot in polling mode for local development."""
    logger.info("Starting bot in polling mode...")
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot is running! Press Ctrl+C to stop.")
    await dp.start_polling(bot)
