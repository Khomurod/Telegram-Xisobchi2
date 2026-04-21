from __future__ import annotations

import asyncio
import random
import re
from html import escape

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
_FALLBACK_BROADCASTS = (
    "Kirim va chiqimlaringizni yozib borsangiz, pulingiz qayerga ketayotganini aniq ko'rasiz. "
    "Shu odat ortiqcha xarajatlarni kamaytirib, jamg'arishni osonlashtiradi. "
    "Moliyaviy erkinlik katta daromaddan emas, pul oqimini nazorat qilishdan boshlanadi.",
    "Har bir xarajatni qayd qilish sizga byudjet ustidan nazorat beradi. "
    "Qayerda tejash va qayerga ko'proq e'tibor berish kerakligini tezroq tushunasiz. "
    "Kichik intizom bugun, katta erkinlik ertaga.",
    "Pulni boshqarish avvalo uni kuzatishdan boshlanadi. "
    "Daromad va xarajatlar yozib borilganda maqsadli jamg'arma qilish ancha osonlashadi. "
    "Moliyaviy erkinlik ana shunday oddiy odatlardan quriladi.",
    "Byudjetni tartibga solish uchun avvalo kirim va chiqimlarni ko'rib turish kerak. "
    "Shunda ortiqcha xarajatlar kamayadi, jamg'arma esa izchil o'sadi. "
    "Moliyaviy erkinlik nazoratli odatlardan boshlanadi.",
    "Pul hisobini yuritish sizga tinchroq va aniqroq moliyaviy qarorlar qilishga yordam beradi. "
    "Qayerda tejash, qayerda ko'proq e'tibor kerakligini tez anglaysiz. "
    "Kirim va chiqim nazorati kelajakdagi erkinlik uchun eng yaxshi tayyorgarlikdir.",
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

_scheduler: AsyncIOScheduler | None = None
_scheduler_lock = asyncio.Lock()


def _normalize_broadcast_text(text: str) -> str:
    return " ".join(text.strip().split())


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
            return f"{escape(generated_text)}{_BROADCAST_CTA}"

        logger.warning("Generated broadcast draft looked low quality; attempting rewrite: %s", generated_text)
        try:
            rewritten_text = await _rewrite_low_quality_broadcast(generated_text)
        except YandexGPTError as exc:
            logger.warning("Broadcast draft rewrite attempt failed; trying another prompt: %s", exc)
            continue

        if not _looks_low_quality_broadcast(rewritten_text):
            return f"{escape(rewritten_text)}{_BROADCAST_CTA}"

    fallback_text = random.choice(_FALLBACK_BROADCASTS)
    logger.warning("Falling back to curated broadcast copy after repeated low-quality AI drafts.")
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
