"""
Minimal keep-alive pinger service.

Deployed on Koyeb — pings the Render bot every 14 minutes
to prevent it from sleeping. Render pings back to keep Koyeb alive.
"""
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("pinger")


async def ping_loop():
    """Periodically ping the target URL to keep it alive."""
    url = settings.PING_TARGET_URL
    interval = settings.PING_INTERVAL_SECONDS
    if not url:
        logger.warning("PING_TARGET_URL not set — pinger disabled")
        return

    logger.info(f"Pinger started: hitting {url} every {interval}s")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    logger.info(f"Ping {url} → {resp.status}")
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
            await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start ping loop on startup, cancel on shutdown."""
    task = asyncio.create_task(ping_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Xisobchi Pinger", lifespan=lifespan)


@app.get("/")
async def health():
    """Health check — Render pings this to keep Koyeb alive."""
    return {"status": "ok", "service": "pinger"}
