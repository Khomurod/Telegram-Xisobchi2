from __future__ import annotations

import asyncio
from html import escape

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot import bot
from app.constants import UZT
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.services.yandex_gpt import get_yandex_gpt_client
from app.utils.logger import setup_logger

logger = setup_logger("broadcaster")

_BROADCAST_PROMPT = (
    "You are an expert financial advisor. Write a short, highly engaging, and unique "
    "motivational message in Uzbek explaining why tracking personal cash flow "
    "(incomes and expenses) leads to financial freedom. Keep it under 4 sentences. "
    "Make it friendly and encouraging. Do NOT use markdown styling."
)
_BROADCAST_CTA = (
    '\n\n👉 <a href="https://t.me/xisobchiman1_bot">XisobchiMan Bot</a> '
    "orqali xarajatlaringizni nazorat qiling!"
)

_scheduler: AsyncIOScheduler | None = None
_scheduler_lock = asyncio.Lock()


async def generate_motivational_broadcast_text() -> str:
    client = get_yandex_gpt_client()
    generated_text = await client.generate_text(
        _BROADCAST_PROMPT,
        temperature=0.8,
        max_tokens=220,
    )
    return f"{escape(generated_text.strip())}{_BROADCAST_CTA}"


async def send_broadcast_text(text: str, *, log_prefix: str = "[Broadcast]") -> dict[str, int]:
    async with async_session() as session:
        user_repo = UserRepository(session)
        telegram_ids = await user_repo.get_all_users()

    success_count = 0
    failure_count = 0
    logger.info("%s Broadcast started for %s users.", log_prefix, len(telegram_ids))

    for tg_id in telegram_ids:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=text,
                parse_mode="HTML",
            )
            success_count += 1
        except Exception:
            failure_count += 1
            logger.error("%s Failed to send message to %s.", log_prefix, tg_id, exc_info=True)

        await asyncio.sleep(0.05)

    logger.info(
        "%s Broadcast finished. successes=%s failures=%s",
        log_prefix,
        success_count,
        failure_count,
    )
    return {
        "sent": success_count,
        "failed": failure_count,
        "total": len(telegram_ids),
    }


async def run_motivational_broadcast() -> None:
    logger.info("[Scheduler] Motivational broadcast started.")

    try:
        final_text = await generate_motivational_broadcast_text()
    except Exception:
        logger.error("[Scheduler] Motivational broadcast setup failed.", exc_info=True)
        return

    await send_broadcast_text(final_text, log_prefix="[Scheduler]")


async def start_broadcaster() -> None:
    global _scheduler

    async with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return

        scheduler = AsyncIOScheduler(timezone=UZT)
        scheduler.add_job(
            run_motivational_broadcast,
            trigger=CronTrigger(day_of_week="mon,wed,fri", hour=9, minute=0, timezone=UZT),
            id="motivational_broadcaster",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        _scheduler = scheduler
        logger.info("[Scheduler] Motivational broadcaster job scheduled successfully.")


async def stop_broadcaster() -> None:
    global _scheduler

    async with _scheduler_lock:
        if _scheduler is None:
            return

        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] Motivational broadcaster stopped.")
