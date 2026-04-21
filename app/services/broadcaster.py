from __future__ import annotations

import asyncio
import json
import random
import re
from html import escape
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot import bot
from app.constants import UZT
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.services.yandex_gpt import YandexGPTError, get_yandex_gpt_client
from app.utils.logger import setup_logger

logger = setup_logger("broadcaster")

_BROADCAST_SYSTEM_PROMPT = (
    "Siz tajribali o'zbek kopirayterisiz. "
    "Faqat tabiiy, ravon va tushunarli o'zbek tilida yozing. "
    "Faqat lotin yozuvidan foydalaning, kirill harflarini umuman ishlatmang. "
    "Sun'iy tarjima ohangi, mavhum iboralar, keraksiz takror va ma'nosiz jumlalar yozmang. "
    "Matn Telegram xabari uchun bo'lsin: qisqa, iliq, ishonchli va motivatsion. "
    "Odamga bevosita 'siz' deb murojaat qiling. "
    "Markdown ishlatmang."
)
_BROADCAST_PROMPT_VARIANTS = (
    "2 yoki 3 gapdan iborat qisqa motivatsion xabar yozing. "
    "Mavzu: kirim va chiqimlarni muntazam yozib borish pul qayerga ketayotganini aniq ko'rsatadi, "
    "ortiqcha xarajatlarni kamaytiradi va moliyaviy erkinlikka yaqinlashtiradi. "
    "Matn samimiy, tabiiy va kundalik o'zbek tilida bo'lsin.",
    "Qisqa va kuchli o'zbekcha xabar yozing. "
    "Asosiy fikr: xarajat va daromad nazorati byudjetni tartibga soladi, jamg'arishni osonlashtiradi "
    "va moliyaviy maqsadlarga tezroq yetishga yordam beradi. "
    "2-3 gapdan oshmasin.",
    "Telegram uchun 2-3 gaplik motivatsion xabar yozing. "
    "Asosiy fikr: pul oqimini kuzatgan odam o'z qarorlarini ongliroq qiladi, "
    "rejani buzayotgan xarajatlarni tezroq ko'radi va moliyaviy intizom hosil qiladi. "
    "Matn tabiiy va ilhomlantiruvchi bo'lsin."
)
_BROADCAST_REWRITE_PROMPT = (
    "Quyidagi matnning mazmunini saqlagan holda uni tabiiy, ravon va ishonchli o'zbek tilida qayta yozing. "
    "Tarjima ohangi, mavhum iboralar va ma'nosiz jumlalarni butunlay olib tashlang. "
    "Natija 2 yoki 3 gap bo'lsin.\n\n"
    "Matn:\n{draft}"
)
_FALLBACK_OPENINGS = (
    "Kirim va chiqimlaringizni yozib borsangiz, pulingiz qayerga ketayotganini aniq ko'rasiz.",
    "Har bir xarajatni qayd qilish sizga byudjet ustidan aniq nazorat beradi.",
    "Pulni boshqarish avvalo uni kuzatishdan boshlanadi.",
    "Byudjetni tartibga solish uchun avvalo kirim va chiqimlarni ko'rib turish kerak.",
    "Pul hisobini yuritish sizga tinchroq va aniqroq moliyaviy qarorlar qilishga yordam beradi.",
    "Daromad va xarajatlarni yozib borish moliyaviy intizomning eng oddiy, lekin eng kuchli odatlaridan biridir.",
    "Kundalik pul hisobini yuritish moliyaviy tartibni kuchaytiradi.",
    "Xarajatlarni yozib borish sizga pul ustidan ko'proq xotirjam nazorat beradi.",
    "Moliyaviy maqsadlarga yaqinlashish har bir sarfni ko'rishdan boshlanadi.",
    "Pul harakatini kuzatish byudjetni boshqarishni ancha soddalashtiradi.",
)
_FALLBACK_BODIES = (
    "Shu odat ortiqcha xarajatlarni kamaytirib, jamg'arishni osonlashtiradi.",
    "Qayerda tejash va qayerga ko'proq e'tibor berish kerakligini tezroq tushunasiz.",
    "Shunda mayda, lekin takrorlanadigan chiqimlar ham ko'zdan qochmaydi.",
    "Nazorat kuchaygani sari jamg'arma qilish ham barqarorroq bo'ladi.",
    "Rejasiz sarf-xarajatlar kamayganda moliyaviy maqsadlarga yetish osonlashadi.",
    "Pul oqimini ko'rib turgan odam qarorlarni ancha ishonch bilan qabul qiladi.",
    "Har bir yozuv sizga qaysi odatlar foydali, qaysilari esa zararli ekanini ko'rsatadi.",
    "Shunda oy oxirida pulning qayerga singib ketgani haqida savol qolmaydi.",
    "Kuzatuv kuchaysa, tejash va jamg'arma qilish qarori ham osonroq bo'ladi.",
    "Aniq raqamlar bilan yashash moliyaviy rejani mustahkamlaydi.",
)
_FALLBACK_CLOSINGS = (
    "Moliyaviy erkinlik katta daromaddan emas, pul oqimini nazorat qilishdan boshlanadi.",
    "Kichik intizom bugun, katta erkinlik ertaga.",
    "Moliyaviy erkinlik ana shunday oddiy odatlardan quriladi.",
    "Moliyaviy barqarorlik har kuni qilinadigan kichik nazoratlardan boshlanadi.",
    "Bugungi tartib ertangi xotirjamlikni yaratadi.",
    "Pulga e'tibor kuchaysa, kelajak rejalari ham aniqroq bo'ladi.",
    "Nazorat bor joyda baraka va ishonch ko'proq bo'ladi.",
    "Bugun yozilgan har bir summa ertangi erkinlikka xizmat qiladi.",
    "Moliyani boshqarish odati vaqt o'tgani sayin eng katta kuchingizga aylanadi.",
    "O'z pul oqimini bilgan odam kelajagini ancha xotirjam quradi.",
)
_BROADCAST_CTA = (
    '\n\n&#128073; <a href="https://t.me/xisobchiman1_bot">XisobchiMan Bot</a> '
    "orqali xarajatlaringizni nazorat qiling!"
)
_LOW_QUALITY_FRAGMENTS = (
    "jarayon qilish",
    "oziq-ovqat va xavfsizlik",
    "hissa-doza",
    "oliyotaraf",
    "har biri uchun imkoniyatlar",
    "xizmatlar va mahsulotlar uchun qancha pul",
    "o'zlashtirishingiz mumkin shuning uchun",
    "o'z ichiga olgan nazorat",
    "kontrol",
    "finans",
    "klich",
    "sovrash",
    "oqishingiz",
    "qarorlarining",
    "intizom qilish",
    "ilhomlantiruvchi bosqich",
)
_QUALITY_MARKERS = (
    "pul qayerga",
    "ortiqcha xarajat",
    "jamg'",
    "byudjet",
    "moliyaviy erkinlik",
)
_FINANCIAL_KEYWORDS = (
    "xarajat",
    "chiqim",
    "daromad",
    "kirim",
    "pul",
    "byudjet",
    "jamg'",
    "tej",
    "nazorat",
    "maqsad",
    "moliyaviy",
    "erkinlik",
)
_BROADCAST_HISTORY_PATH = Path("data") / "broadcast_history.json"
_FALLBACK_STATE_PATH = Path("data") / "broadcast_fallback_state.json"
_broadcast_history_lock = asyncio.Lock()
_used_broadcast_keys: set[str] | None = None
_fallback_state: dict[str, object] | None = None

_scheduler: AsyncIOScheduler | None = None
_scheduler_lock = asyncio.Lock()


def _normalize_broadcast_text(text: str) -> str:
    return " ".join(text.strip().split())


def _broadcast_history_key(text: str) -> str:
    return _normalize_broadcast_text(text).casefold()


def _build_default_fallback_state() -> dict[str, object]:
    opening_order = list(_FALLBACK_OPENINGS)
    body_order = list(_FALLBACK_BODIES)
    closing_order = list(_FALLBACK_CLOSINGS)
    random.shuffle(opening_order)
    random.shuffle(body_order)
    random.shuffle(closing_order)
    return {
        "opening_order": opening_order,
        "opening_index": 0,
        "opening_last": "",
        "body_order": body_order,
        "body_index": 0,
        "body_last": "",
        "closing_order": closing_order,
        "closing_index": 0,
        "closing_last": "",
    }


def _looks_low_quality_broadcast(text: str) -> bool:
    normalized = _normalize_broadcast_text(text)
    lowered = normalized.lower()

    if not normalized:
        return True

    if re.search(r"[А-Яа-яЁё]", normalized):
        return True

    for fragment in _LOW_QUALITY_FRAGMENTS:
        if fragment in lowered:
            return True

    words = re.findall(r"[A-Za-zÀ-ÿ'-]+", lowered)
    if len(words) < 12 or len(words) > 70:
        return True

    sentence_count = len(re.findall(r"[.!?]", normalized))
    if sentence_count < 2 or sentence_count > 4:
        return True

    financial_hits = {keyword for keyword in _FINANCIAL_KEYWORDS if keyword in lowered}
    if len(financial_hits) < 2:
        return True

    quality_hits = {marker for marker in _QUALITY_MARKERS if marker in lowered}
    if len(quality_hits) < 2:
        return True

    if any(len(word) > 18 for word in words):
        return True

    unique_ratio = len(set(words)) / len(words)
    return unique_ratio < 0.5


async def _generate_broadcast_candidate(prompt: str) -> str:
    client = get_yandex_gpt_client()
    generated_text = await client.generate_text(
        prompt,
        system_prompt=_BROADCAST_SYSTEM_PROMPT,
        temperature=0.25,
        max_tokens=180,
    )
    return _normalize_broadcast_text(generated_text)


async def _rewrite_low_quality_broadcast(draft: str) -> str:
    client = get_yandex_gpt_client()
    rewritten_text = await client.generate_text(
        _BROADCAST_REWRITE_PROMPT.format(draft=draft),
        system_prompt=_BROADCAST_SYSTEM_PROMPT,
        temperature=0.1,
        max_tokens=180,
    )
    return _normalize_broadcast_text(rewritten_text)


def _read_broadcast_history_file(path: Path) -> set[str]:
    if not path.exists():
        return set()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Broadcast history file could not be read; starting with empty history.")
        return set()

    if not isinstance(payload, dict):
        return set()

    raw_messages = payload.get("messages", [])
    if not isinstance(raw_messages, list):
        return set()

    return {
        str(item)
        for item in raw_messages
        if isinstance(item, str) and item.strip()
    }


def _write_broadcast_history_file(path: Path, keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps({"messages": sorted(keys)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _read_fallback_state_file(path: Path) -> dict[str, object]:
    default_state = _build_default_fallback_state()
    if not path.exists():
        return default_state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Fallback state file could not be read; regenerating fallback order.")
        return default_state

    if not isinstance(payload, dict):
        return default_state

    state = default_state.copy()
    for key in default_state:
        value = payload.get(key)
        if isinstance(default_state[key], list):
            if isinstance(value, list) and value:
                state[key] = [str(item) for item in value if isinstance(item, str)]
        elif isinstance(default_state[key], int):
            if isinstance(value, int):
                state[key] = value
        elif isinstance(default_state[key], str):
            if isinstance(value, str):
                state[key] = value

    return state


def _write_fallback_state_file(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


async def _load_broadcast_history() -> set[str]:
    global _used_broadcast_keys

    if _used_broadcast_keys is not None:
        return _used_broadcast_keys

    loaded = await asyncio.to_thread(_read_broadcast_history_file, _BROADCAST_HISTORY_PATH)
    _used_broadcast_keys = loaded
    return _used_broadcast_keys


async def _load_fallback_state() -> dict[str, object]:
    global _fallback_state

    if _fallback_state is not None:
        return _fallback_state

    loaded = await asyncio.to_thread(_read_fallback_state_file, _FALLBACK_STATE_PATH)
    _fallback_state = loaded
    return _fallback_state


async def _reserve_unique_broadcast_text(text: str) -> bool:
    key = _broadcast_history_key(text)

    async with _broadcast_history_lock:
        history = await _load_broadcast_history()
        if key in history:
            return False

        history.add(key)
        await asyncio.to_thread(_write_broadcast_history_file, _BROADCAST_HISTORY_PATH, history)
        return True


def _next_fallback_component(
    state: dict[str, object],
    *,
    prefix: str,
    options: tuple[str, ...],
) -> str:
    order_key = f"{prefix}_order"
    index_key = f"{prefix}_index"
    last_key = f"{prefix}_last"

    order = state.get(order_key)
    index = state.get(index_key)
    last_value = str(state.get(last_key) or "")

    normalized_options = list(options)
    if not isinstance(order, list) or sorted(order) != sorted(normalized_options):
        order = normalized_options[:]
        random.shuffle(order)
        if len(order) > 1 and order[0] == last_value:
            order.append(order.pop(0))
        index = 0

    if not isinstance(index, int) or index >= len(order):
        order = normalized_options[:]
        random.shuffle(order)
        if len(order) > 1 and order[0] == last_value:
            order.append(order.pop(0))
        index = 0

    choice = order[index]
    state[order_key] = order
    state[index_key] = index + 1
    state[last_key] = choice
    return choice


async def _compose_unique_fallback_broadcast_text() -> str | None:
    async with _broadcast_history_lock:
        history = await _load_broadcast_history()
        fallback_state = await _load_fallback_state()

        for _ in range(len(_FALLBACK_OPENINGS) * len(_FALLBACK_BODIES) * len(_FALLBACK_CLOSINGS)):
            opening = _next_fallback_component(
                fallback_state,
                prefix="opening",
                options=_FALLBACK_OPENINGS,
            )
            body = _next_fallback_component(
                fallback_state,
                prefix="body",
                options=_FALLBACK_BODIES,
            )
            closing = _next_fallback_component(
                fallback_state,
                prefix="closing",
                options=_FALLBACK_CLOSINGS,
            )
            chosen = f"{opening} {body} {closing}"
            key = _broadcast_history_key(chosen)
            if key in history:
                continue

            history.add(key)
            await asyncio.to_thread(_write_broadcast_history_file, _BROADCAST_HISTORY_PATH, history)
            await asyncio.to_thread(_write_fallback_state_file, _FALLBACK_STATE_PATH, fallback_state)
            return chosen

        return None


async def _finalize_unique_broadcast(raw_text: str) -> str | None:
    normalized = _normalize_broadcast_text(raw_text)
    if not normalized:
        return None

    if not await _reserve_unique_broadcast_text(normalized):
        logger.info("Broadcast candidate skipped because it was already used before.")
        return None

    return f"{escape(normalized)}{_BROADCAST_CTA}"


async def generate_motivational_broadcast_text() -> str:
    prompt_variants = list(_BROADCAST_PROMPT_VARIANTS)
    random.shuffle(prompt_variants)

    for prompt in prompt_variants:
        try:
            generated_text = await _generate_broadcast_candidate(prompt)
        except YandexGPTError as exc:
            logger.warning("Broadcast draft generation attempt failed; trying another prompt: %s", exc)
            continue

        if not _looks_low_quality_broadcast(generated_text):
            final_text = await _finalize_unique_broadcast(generated_text)
            if final_text is not None:
                return final_text

        logger.warning("Generated broadcast draft looked low quality; attempting rewrite: %s", generated_text)
        try:
            rewritten_text = await _rewrite_low_quality_broadcast(generated_text)
        except YandexGPTError as exc:
            logger.warning("Broadcast draft rewrite attempt failed; trying another prompt: %s", exc)
            continue

        if not _looks_low_quality_broadcast(rewritten_text):
            final_text = await _finalize_unique_broadcast(rewritten_text)
            if final_text is not None:
                return final_text

    fallback_text = await _compose_unique_fallback_broadcast_text()
    if fallback_text is None:
        raise RuntimeError("All curated fallback broadcast messages have been exhausted.")

    logger.warning("Falling back to curated composed broadcast copy after repeated low-quality AI drafts.")
    return f"{escape(fallback_text)}{_BROADCAST_CTA}"


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
