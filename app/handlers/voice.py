import asyncio
import time
from collections import defaultdict

from aiogram import Bot, F, Router, types
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES
from app.database.connection import async_session
from app.database.repositories.transaction import TransactionRepository
from app.database.repositories.user import UserRepository
from app.services.parser import parse_transactions
from app.services.phone_prompt import send_phone_prompt
from app.services.speech_service import (
    schedule_whisper_shadow_log,
    should_run_whisper_shadow_test,
    transcribe_audio,
    transcribe_audio_whisper_test,
)
from app.services.transaction import TransactionService
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("voice_handler")
router = Router()

_user_timestamps: dict[int, list[float]] = defaultdict(list)
_PENDING_TTL = 300.0  # 5 minutes
_pending_confirmations: dict[str, dict] = {}


def _check_rate_limit(user_id: int) -> bool:
    """Return True if user is within rate limit, False if exceeded."""
    now = time.time()
    window = 60.0
    limit = settings.VOICE_RATE_LIMIT
    recent = [t for t in _user_timestamps.get(user_id, []) if now - t < window]

    if recent:
        _user_timestamps[user_id] = recent
    else:
        _user_timestamps.pop(user_id, None)

    if len(recent) >= limit:
        return False

    _user_timestamps.setdefault(user_id, []).append(now)
    return True


def _cleanup_stale_pending() -> None:
    """Remove pending confirmations older than TTL to prevent memory leaks."""
    now = time.time()
    stale = [k for k, v in _pending_confirmations.items() if now - v.get("created_at", 0) > _PENDING_TTL]
    for key in stale:
        logger.debug("Discarding stale pending confirmation: %s", key)
        _pending_confirmations.pop(key, None)


async def _maybe_send_phone_prompt(
    callback: CallbackQuery,
    telegram_id: int,
    should_request_phone: bool,
) -> None:
    if not should_request_phone:
        return

    try:
        await send_phone_prompt(callback.bot, telegram_id)
    except Exception as exc:
        logger.error(
            "Failed to send delayed phone prompt to user %s: %s",
            telegram_id,
            exc,
            exc_info=True,
        )


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot, state: FSMContext):
    """Full voice -> transcribe -> parse -> confirm -> store pipeline."""
    if await state.get_state():
        return

    user_id = message.from_user.id
    duration = message.voice.duration
    logger.info("Voice message from user %s, duration: %ss", user_id, duration)

    _cleanup_stale_pending()

    if duration > settings.MAX_VOICE_DURATION:
        await message.answer(
            f"⏱ Ovozli xabar juda uzun ({duration}s).\n"
            f"Maksimal davomiylik: {settings.MAX_VOICE_DURATION} soniya."
        )
        return

    if not _check_rate_limit(user_id):
        await message.answer(
            "⚠️ Juda ko'p ovozli xabar yubordingiz.\n"
            "Iltimos, 1 daqiqa kutib, qaytadan urinib ko'ring."
        )
        logger.warning("Rate limit exceeded for user %s", user_id)
        return

    processing_msg = await message.answer("⏳")
    whisper_task: asyncio.Task | None = None

    try:
        file = await bot.get_file(message.voice.file_id)
        audio_io = await bot.download_file(file.file_path)
        audio_bytes = audio_io.read()
        logger.info("Downloaded voice to memory: %s bytes", f"{len(audio_bytes):,}")

        if should_run_whisper_shadow_test(user_id):
            whisper_task = asyncio.create_task(
                transcribe_audio_whisper_test(
                    audio_bytes,
                    filename=f"{message.voice.file_id}.ogg",
                )
            )

        result = await transcribe_audio(audio_bytes)
        if whisper_task is not None:
            schedule_whisper_shadow_log(
                whisper_task=whisper_task,
                yandex_result=result,
                user_id=user_id,
                message_id=message.message_id,
            )

        if not result.text:
            await processing_msg.edit_text(
                "❌ Ovozli xabaringizni tushunolmadim.\n"
                "Iltimos, aniqroq gapirib, qaytadan yuboring."
            )
            return

        parsed_list = await parse_transactions(result.text)
        if not parsed_list:
            await processing_msg.edit_text(
                "🤔 Summani aniqlay olmadim.\n"
                "Iltimos, aniqroq ayting. Masalan:\n"
                "\"Ovqatga 50 ming so'm sarfladim\""
            )
            return

        confirm_key = f"{user_id}_{message.message_id}"
        _pending_confirmations[confirm_key] = {
            "telegram_id": user_id,
            "first_name": message.from_user.first_name,
            "username": message.from_user.username,
            "text": result.text,
            "parsed_list": parsed_list,
            "confidence": result.confidence,
            "created_at": time.time(),
        }

        conf_warning = ""
        if result.confidence < 0.6:
            conf_warning = "\n⚠️ _Ovoz sifati past. Iltimos, tekshiring._\n"

        confirm_text = _build_confirm_text(parsed_list, result.text, conf_warning)
        btn_label = "✅ Ha, barchasini saqlash" if len(parsed_list) > 1 else "✅ Ha, saqlash"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=btn_label,
                        callback_data=f"confirm_{confirm_key}",
                        style=ButtonStyle.SUCCESS,
                    ),
                    InlineKeyboardButton(
                        text="❌ Yo'q",
                        callback_data=f"cancel_{confirm_key}",
                        style=ButtonStyle.DANGER,
                    ),
                ]
            ]
        )

        await processing_msg.edit_text(confirm_text, parse_mode="Markdown", reply_markup=keyboard)
        logger.info(
            "Confirmation sent to user %s: %s txn(s) (conf: %.2f)",
            user_id,
            len(parsed_list),
            result.confidence,
        )

    except FileNotFoundError as exc:
        if whisper_task is not None and not whisper_task.done():
            whisper_task.cancel()
        logger.error("Credentials error: %s", exc)
        await processing_msg.edit_text(
            "⚠️ Tizim sozlamalari noto'g'ri.\nIltimos, administratorga murojaat qiling."
        )
    except Exception as exc:
        if whisper_task is not None and not whisper_task.done():
            whisper_task.cancel()
        logger.error("Voice processing error for user %s: %s", user_id, exc, exc_info=True)
        try:
            await processing_msg.edit_text(
                "⚠️ Tizimda xatolik yuz berdi.\n"
                "Iltimos, ovozni yana bir bor aniqroq yuboring."
            )
        except Exception:
            pass


def _build_confirm_text(
    parsed_list: list,
    raw_text: str,
    conf_warning: str = "",
) -> str:
    """Build a confirmation message for one or more parsed transactions."""
    if len(parsed_list) == 1:
        parsed = parsed_list[0]
        type_uz = "Kirim" if parsed.type == "income" else "Chiqim"
        emoji = "📈" if parsed.type == "income" else "📉"
        cat_emoji = CATEGORY_EMOJI.get(parsed.category, "📦")
        cat_name = CATEGORY_NAMES.get(parsed.category, parsed.category)
        amount_str = format_amount(parsed.amount, parsed.currency)
        return (
            f"{emoji} *{type_uz}*\n"
            f"💵 {amount_str}\n"
            f"{cat_emoji} {cat_name}\n\n"
            f"📝 _{raw_text}_\n"
            f"{conf_warning}\n"
            "Shu ma'lumot to'g'rimi?"
        )

    lines = [f"📋 *{len(parsed_list)} ta operatsiya topildi:*\n"]
    for index, parsed in enumerate(parsed_list, 1):
        emoji = "📈" if parsed.type == "income" else "📉"
        type_uz = "Kirim" if parsed.type == "income" else "Chiqim"
        cat_emoji = CATEGORY_EMOJI.get(parsed.category, "📦")
        cat_name = CATEGORY_NAMES.get(parsed.category, parsed.category)
        amount_str = format_amount(parsed.amount, parsed.currency)
        lines.append(
            f"*{index}.* {emoji} {type_uz} — {amount_str}\n"
            f"     {cat_emoji} {cat_name}"
        )

    lines.append(f"\n📝 _{raw_text}_")
    if conf_warning:
        lines.append(conf_warning)
    lines.append("\nBarchasini saqlaymizmi?")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("confirm_"))
async def handle_confirm(callback: CallbackQuery):
    """Save all parsed transactions after user confirms."""
    confirm_key = callback.data.replace("confirm_", "")
    pending = _pending_confirmations.pop(confirm_key, None)

    if not pending:
        await callback.answer("Bu operatsiya eskirgan. Qaytadan yuboring.", show_alert=True)
        return

    parsed_list = pending.get("parsed_list") or ([pending["parsed"]] if "parsed" in pending else [])

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            txn_repo = TransactionRepository(session)
            service = TransactionService(user_repo, txn_repo)

            if len(parsed_list) == 1:
                result = await service.save_parsed(
                    telegram_id=pending["telegram_id"],
                    parsed=parsed_list[0],
                    first_name=pending["first_name"],
                    username=pending["username"],
                )
                if result["success"]:
                    txn = result["transaction"]
                    emoji = "📈" if txn["type"] == "income" else "📉"
                    type_uz = "Kirim" if txn["type"] == "income" else "Chiqim"
                    cat_emoji = CATEGORY_EMOJI.get(txn["category"], "📦")
                    amount_str = format_amount(txn["amount"], txn["currency"])
                    response = (
                        "✅ Operatsiya saqlandi!\n\n"
                        f"{emoji} *Tur:* {type_uz}\n"
                        f"💵 *Summa:* {amount_str}\n"
                        f"{cat_emoji} *Kategoriya:* {txn['category']}\n"
                    )
                    await callback.message.edit_text(response, parse_mode="Markdown")
                    await _maybe_send_phone_prompt(
                        callback=callback,
                        telegram_id=pending["telegram_id"],
                        should_request_phone=result.get("should_request_phone", False),
                    )
                else:
                    await callback.message.edit_text(
                        "⚠️ Saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring."
                    )
            else:
                result = await service.save_parsed_batch(
                    telegram_id=pending["telegram_id"],
                    parsed_list=parsed_list,
                    first_name=pending["first_name"],
                    username=pending["username"],
                )
                if result["success"]:
                    lines = [f"✅ *{result['count']} ta operatsiya saqlandi!*\n"]
                    for index, txn in enumerate(result["transactions"], 1):
                        emoji = "📈" if txn["type"] == "income" else "📉"
                        cat_emoji = CATEGORY_EMOJI.get(txn["category"], "📦")
                        amount_str = format_amount(txn["amount"], txn["currency"])
                        lines.append(f"{index}. {emoji} {amount_str} — {cat_emoji} {txn['category']}")
                    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
                    await _maybe_send_phone_prompt(
                        callback=callback,
                        telegram_id=pending["telegram_id"],
                        should_request_phone=result.get("should_request_phone", False),
                    )
                else:
                    await callback.message.edit_text(
                        "⚠️ Saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring."
                    )

        logger.info(
            "%s transaction(s) confirmed and saved for user %s",
            len(parsed_list),
            pending["telegram_id"],
        )

    except Exception as exc:
        logger.error("Confirmation error: %s", exc, exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"))
async def handle_cancel(callback: CallbackQuery):
    """Cancel transaction(s) - don't save."""
    confirm_key = callback.data.replace("cancel_", "")
    _pending_confirmations.pop(confirm_key, None)

    await callback.message.edit_text("🚫 Operatsiya bekor qilindi.")
    await callback.answer()
    logger.info("Transaction cancelled by user %s", callback.from_user.id)
