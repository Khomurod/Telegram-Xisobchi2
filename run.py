"""
Xisobchi Bot — Uzbek Voice Expense Tracker
Entry point for running the bot.
"""
import asyncio
from app.config import settings


def main():
    if settings.is_webhook:
        # Webhook mode — run FastAPI with uvicorn (Render)
        import os
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
    elif settings.MODE == "pinger":
        # Pinger mode — run minimal keep-alive service (Koyeb)
        import os
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run("app.pinger:app", host="0.0.0.0", port=port, reload=False)
    else:
        # Polling mode — run aiogram polling (local dev)
        from app.main import start_polling
        asyncio.run(start_polling())


if __name__ == "__main__":
    main()
