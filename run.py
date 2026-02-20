"""
Xisobchi Bot — Uzbek Voice Expense Tracker
Entry point for running the bot.
"""
import asyncio
from app.config import settings


def main():
    if settings.is_webhook:
        # Webhook mode — run FastAPI with uvicorn
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    else:
        # Polling mode — run aiogram polling
        from app.main import start_polling
        asyncio.run(start_polling())


if __name__ == "__main__":
    main()
