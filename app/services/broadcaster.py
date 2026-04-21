from __future__ import annotations

import asyncio
import json
import re
from html import escape
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot import bot
from app.constants import UZT
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.utils.logger import setup_logger

logger = setup_logger("broadcaster")

_BROADCAST_CTA = (
    '\n\n&#128073; <a href="https://t.me/xisobchiman1_bot">XisobchiMan Bot</a> '
    "orqali xarajatlaringizni nazorat qiling!"
)
_BROADCAST_POOL_PATH = Path("data") / "broadcast_pool.json"
_MAX_POOL_MESSAGES = 500
_ALLOWED_BROADCAST_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_pool_lock = asyncio.Lock()
_pool_state: dict[str, Any] | None = None

_scheduler: AsyncIOScheduler | None = None
_scheduler_lock = asyncio.Lock()


def _normalize_message_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    return collapsed[:4096]


def _render_broadcast_message(message: str) -> str:
    return f"{escape(message)}{_BROADCAST_CTA}"


def _default_schedule() -> dict[str, Any]:
    return {
        "enabled": True,
        "days": ["mon", "wed", "fri"],
        "hour": 9,
        "minute": 0,
    }


def _sanitize_schedule(raw: Any) -> dict[str, Any]:
    schedule = _default_schedule()
    if not isinstance(raw, dict):
        return schedule

    schedule["enabled"] = bool(raw.get("enabled", schedule["enabled"]))

    if "days" in raw:
        raw_days = raw.get("days")
        candidates: list[Any]
        if isinstance(raw_days, str):
            candidates = raw_days.split(",")
        elif isinstance(raw_days, list):
            candidates = raw_days
        else:
            candidates = []

        unique_days: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if not isinstance(item, str):
                continue
            day = item.strip().lower()
            if day not in _ALLOWED_BROADCAST_DAYS or day in seen:
                continue
            seen.add(day)
            unique_days.append(day)
        schedule["days"] = unique_days

    try:
        hour = int(raw.get("hour", schedule["hour"]))
    except (TypeError, ValueError):
        hour = schedule["hour"]
    schedule["hour"] = hour if 0 <= hour <= 23 else schedule["hour"]

    try:
        minute = int(raw.get("minute", schedule["minute"]))
    except (TypeError, ValueError):
        minute = schedule["minute"]
    schedule["minute"] = minute if 0 <= minute <= 59 else schedule["minute"]

    return schedule


def _default_pool_state() -> dict[str, Any]:
    return {
        "messages": [],
        "next_index": 0,
        "schedule": _default_schedule(),
    }


def _read_broadcast_pool_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_pool_state()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Broadcast pool file could not be read; using an empty pool.")
        return _default_pool_state()

    if not isinstance(payload, dict):
        return _default_pool_state()

    raw_messages = payload.get("messages", [])
    next_index = payload.get("next_index", 0)
    schedule = _sanitize_schedule(payload.get("schedule"))

    if not isinstance(raw_messages, list):
        raw_messages = []
    if not isinstance(next_index, int):
        next_index = 0

    messages = [
        normalized
        for item in raw_messages
        if isinstance(item, str)
        for normalized in [_normalize_message_text(item)]
        if normalized
    ]

    next_index = max(0, min(next_index, len(messages)))
    return {
        "messages": messages,
        "next_index": next_index,
        "schedule": schedule,
    }


def _write_broadcast_pool_file(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _parse_pool_messages(raw_text: str) -> list[str]:
    chunks = re.split(r"(?:\r?\n\s*){2,}", (raw_text or "").strip())
    messages: list[str] = []
    seen: set[str] = set()

    for chunk in chunks:
        normalized = _normalize_message_text(chunk)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        messages.append(normalized)

    return messages[:_MAX_POOL_MESSAGES]


async def _load_pool_state() -> dict[str, Any]:
    global _pool_state

    if _pool_state is not None:
        return _pool_state

    loaded = await asyncio.to_thread(_read_broadcast_pool_file, _BROADCAST_POOL_PATH)
    _pool_state = loaded
    return _pool_state


async def _persist_pool_state(state: dict[str, Any]) -> None:
    await asyncio.to_thread(_write_broadcast_pool_file, _BROADCAST_POOL_PATH, state)


def _build_schedule_trigger(schedule: dict[str, Any]) -> CronTrigger | None:
    sanitized = _sanitize_schedule(schedule)
    if not sanitized["enabled"] or not sanitized["days"]:
        return None

    return CronTrigger(
        day_of_week=",".join(sanitized["days"]),
        hour=sanitized["hour"],
        minute=sanitized["minute"],
        timezone=UZT,
    )


async def _sync_scheduler_from_state(state: dict[str, Any]) -> None:
    schedule = _sanitize_schedule(state.get("schedule"))

    async with _scheduler_lock:
        if _scheduler is None:
            return

        trigger = _build_schedule_trigger(schedule)
        job = _scheduler.get_job("motivational_broadcaster")

        if trigger is None:
            if job is not None:
                _scheduler.remove_job("motivational_broadcaster")
            logger.info("[Scheduler] Motivational broadcaster is paused or has no active weekdays.")
            return

        if job is None:
            _scheduler.add_job(
                run_motivational_broadcast,
                trigger=trigger,
                id="motivational_broadcaster",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        else:
            job.reschedule(trigger=trigger)
            job.modify(max_instances=1, coalesce=True)

        logger.info(
            "[Scheduler] Motivational broadcaster job scheduled successfully. days=%s time=%02d:%02d UZT",
            ",".join(schedule["days"]),
            schedule["hour"],
            schedule["minute"],
        )


async def _get_scheduler_next_run_at() -> str | None:
    async with _scheduler_lock:
        if _scheduler is None:
            return None

        job = _scheduler.get_job("motivational_broadcaster")
        next_run = job.next_run_time if job is not None else None
        return next_run.isoformat() if next_run is not None else None


async def get_broadcast_pool_status() -> dict[str, Any]:
    async with _pool_lock:
        state = await _load_pool_state()
        messages = list(state["messages"])
        next_index = int(state["next_index"])
        schedule = _sanitize_schedule(state.get("schedule"))
        total = len(messages)
        remaining = max(total - next_index, 0)
        next_message = messages[next_index] if next_index < total else ""

    return {
        "messages": messages,
        "total": total,
        "next_index": next_index,
        "next_position": next_index + 1 if next_message else 0,
        "remaining": remaining,
        "next_message": next_message,
        "schedule": schedule,
        "next_run_at": await _get_scheduler_next_run_at(),
    }


async def save_broadcast_pool(raw_text: str, schedule: dict[str, Any] | None = None) -> dict[str, Any]:
    messages = _parse_pool_messages(raw_text)
    sanitized_schedule = _sanitize_schedule(schedule) if schedule is not None else None

    async with _pool_lock:
        state = await _load_pool_state()
        state["messages"] = messages
        state["next_index"] = 0
        if sanitized_schedule is not None:
            state["schedule"] = sanitized_schedule
        await _persist_pool_state(state)

    await _sync_scheduler_from_state(state)
    logger.info("Broadcast pool saved. total_messages=%s", len(messages))
    return await get_broadcast_pool_status()


async def reset_broadcast_pool_cursor() -> dict[str, Any]:
    async with _pool_lock:
        state = await _load_pool_state()
        state["next_index"] = 0
        await _persist_pool_state(state)

    logger.info("Broadcast pool cursor reset to the first message.")
    return await get_broadcast_pool_status()


async def preview_next_broadcast_text() -> str | None:
    async with _pool_lock:
        state = await _load_pool_state()
        messages = state["messages"]
        next_index = int(state["next_index"])
        if next_index >= len(messages):
            return None
        return _render_broadcast_message(messages[next_index])


async def consume_next_broadcast_text() -> str | None:
    async with _pool_lock:
        state = await _load_pool_state()
        messages = state["messages"]
        next_index = int(state["next_index"])
        if next_index >= len(messages):
            return None

        message = messages[next_index]
        state["next_index"] = next_index + 1
        await _persist_pool_state(state)

    return _render_broadcast_message(message)


async def generate_motivational_broadcast_text() -> str:
    preview = await preview_next_broadcast_text()
    if preview is None:
        raise RuntimeError("Broadcast pool is empty or exhausted.")
    return preview


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
        final_text = await consume_next_broadcast_text()
    except Exception:
        logger.error("[Scheduler] Could not load the next scheduled broadcast.", exc_info=True)
        return

    if not final_text:
        logger.warning("[Scheduler] Broadcast pool is empty or exhausted; skipping scheduled send.")
        return

    await send_broadcast_text(final_text, log_prefix="[Scheduler]")


async def start_broadcaster() -> None:
    global _scheduler

    async with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return

        scheduler = AsyncIOScheduler(timezone=UZT)
        scheduler.start()
        _scheduler = scheduler

    state = await _load_pool_state()
    await _sync_scheduler_from_state(state)


async def stop_broadcaster() -> None:
    global _scheduler

    async with _scheduler_lock:
        if _scheduler is None:
            return

        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] Motivational broadcaster stopped.")
