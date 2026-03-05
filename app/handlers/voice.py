import time
from collections import defaultdict
from aiogram import Router, types, F, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ButtonStyle
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.speech_service import transcribe_audio
from app.services.parser import parse_transactions
from app.services.transaction import TransactionService
from app.config import settings
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("voice_handler")
router = Router()

# ── Rate limiter (in-memory) ─────────────────────────────────

_user_timestamps: dict[int, list[float]] = defaultdict(list)

_PENDING_TTL = 300.0  # 5 minutes — confirmations older than this are discarded


def _check_rate_limit(user_id: int) -> bool:
    """Return True if user is within rate limit, False if exceeded."""
    now = time.time()
    window = 60.0  # 1 minute
    limit = settings.VOICE_RATE_LIMIT

    # Use .get() to avoid defaultdict auto-creating an empty entry
    recent = [t for t in _user_timestamps.get(user_id, []) if now - t < window]

    if recent:
        _user_timestamps[user_id] = recent
    else:
        # Remove the key entirely to keep memory clean
        _user_timestamps.pop(user_id, None)

    if len(recent) >= limit:
        return False

    # Within limit — record this request
    _user_timestamps.setdefault(user_id, []).append(now)
    return True



# ── Pending confirmations (in-memory) with TTL ───────────────

_pending_confirmations: dict[str, dict] = {}


def _cleanup_stale_pending() -> None:
    """Remove pending confirmations older than TTL to prevent memory leaks."""
    now = time.time()
    stale = [k for k, v in _pending_confirmations.items() if now - v.get("created_at", 0) > _PENDING_TTL]
    for k in stale:
        logger.debug(f"Discarding stale pending confirmation: {k}")
        _pending_confirmations.pop(k, None)


# ── Voice message handler ────────────────────────────────────

@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    """Full voice → transcribe → parse → confirm → store pipeline."""
    user_id = message.from_user.id
    duration = message.voice.duration
    logger.info(f"Voice message from user {user_id}, duration: {duration}s")

    # Clean up stale confirmations on every incoming voice message
    _cleanup_stale_pending()

    # Guard 1: Duration limit
    if duration > settings.MAX_VOICE_DURATION:
        await message.answer(
            f"⏱ Ovozli xabar juda uzun ({duration}s).\n"
            f"Maksimal davomiylik: {settings.MAX_VOICE_DURATION} soniya."
        )
        return

    # Guard 2: Rate limit
    if not _check_rate_limit(user_id):
        await message.answer(
            "⚠️ Juda ko'p ovozli xabar yubordingiz.\n"
            "Iltimos, 1 daqiqa kutib, qaytadan urinib ko'ring."
        )
        logger.warning(f"Rate limit exceeded for user {user_id}")
        return

    # Step 1: Acknowledge receipt
    processing_msg = await message.answer("⏳")

    try:
        # Step 2: Download voice file to memory (no disk I/O)
        file = await bot.get_file(message.voice.file_id)
        audio_io = await bot.download_file(file.file_path)
        audio_bytes = audio_io.read()
        logger.info(f"Downloaded voice to memory: {len(audio_bytes):,} bytes")

        # Step 3: Transcribe with Whisper (async, in-memory)
        result = await transcribe_audio(audio_bytes)

        if not result.text:
            await processing_msg.edit_text(
                "❌ Ovozli xabaringizni tushunolmadim.\n"
                "Iltimos, aniqroq gapirib, qaytadan yuboring."
            )
            return

        # Step 4: Parse transaction(s) — supports multiple in one message
        parsed_list = parse_transactions(result.text)

        if not parsed_list:
            await processing_msg.edit_text(
                "🤔 Summani aniqlay olmadim.\n"
                "Iltimos, aniqroq ayting. Masalan:\n"
                "\"Ovqatga 50 ming so'm sarfladim\""
            )
            return

        # Step 5: Store pending confirmation with all parsed results
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

        # Step 6: Build confirmation message
        conf_warning = ""
        if result.confidence < 0.6:
            conf_warning = "\n⚠️ _Ovoz sifati past. Iltimos, tekshiring._\n"

        confirm_text = _build_confirm_text(parsed_list, result.text, conf_warning)

        btn_label = "✅ Ha, barchasini saqlash" if len(parsed_list) > 1 else "✅ Ha, saqlash"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_label, callback_data=f"confirm_{confirm_key}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=f"cancel_{confirm_key}", style=ButtonStyle.DANGER),
            ]
        ])

        await processing_msg.edit_text(confirm_text, parse_mode="Markdown", reply_markup=keyboard)
        logger.info(f"Confirmation sent to user {user_id}: {len(parsed_list)} txn(s) (conf: {result.confidence:.2f})")

    except FileNotFoundError as e:
        logger.error(f"Credentials error: {e}")
        await processing_msg.edit_text(
            "⚠️ Tizim sozlamalari noto'g'ri.\nIltimos, administratorga murojaat qiling."
        )
    except Exception as e:
        logger.error(f"Voice processing error for user {user_id}: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(
                "⚠️ Tizimda xatolik yuz berdi.\n"
                "Iltimos, ovozni yana bir bor aniqroq yuboring."
            )
        except Exception:
            pass


# ── Confirmation message builder ─────────────────────────────

def _build_confirm_text(
    parsed_list: list,
    raw_text: str,
    conf_warning: str = "",
) -> str:
    """Build a confirmation message for one or more parsed transactions."""
    if len(parsed_list) == 1:
        # Single transaction — same compact format as before
        p = parsed_list[0]
        type_uz = "Kirim" if p.type == "income" else "Chiqim"
        emoji = "📈" if p.type == "income" else "📉"
        cat_emoji = CATEGORY_EMOJI.get(p.category, "📦")
        cat_name = CATEGORY_NAMES.get(p.category, p.category)
        amount_str = format_amount(p.amount, p.currency)
        return (
            f"{emoji} *{type_uz}*\n"
            f"💵 {amount_str}\n"
            f"{cat_emoji} {cat_name}\n\n"
            f"📝 _{raw_text}_\n"
            f"{conf_warning}\n"
            f"Shu ma'lumot to'g'rimi?"
        )

    # Multiple transactions — numbered list
    lines = [f"📋 *{len(parsed_list)} ta operatsiya topildi:*\n"]
    for i, p in enumerate(parsed_list, 1):
        emoji = "📈" if p.type == "income" else "📉"
        type_uz = "Kirim" if p.type == "income" else "Chiqim"
        cat_emoji = CATEGORY_EMOJI.get(p.category, "📦")
        cat_name = CATEGORY_NAMES.get(p.category, p.category)
        amount_str = format_amount(p.amount, p.currency)
        lines.append(
            f"*{i}.* {emoji} {type_uz} — {amount_str}\n"
            f"     {cat_emoji} {cat_name}"
        )

    lines.append(f"\n📝 _{raw_text}_")
    if conf_warning:
        lines.append(conf_warning)
    lines.append("\nBarchasini saqlaymizmi?")
    return "\n".join(lines)


# ── Confirmation callbacks ───────────────────────────────────

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
                        f"✅ Operatsiya saqlandi!\n\n"
                        f"{emoji} *Tur:* {type_uz}\n"
                        f"💵 *Summa:* {amount_str}\n"
                        f"{cat_emoji} *Kategoriya:* {txn['category']}\n"
                    )
                    await callback.message.edit_text(response, parse_mode="Markdown")
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
                    for i, txn in enumerate(result["transactions"], 1):
                        emoji = "📈" if txn["type"] == "income" else "📉"
                        cat_emoji = CATEGORY_EMOJI.get(txn["category"], "📦")
                        amount_str = format_amount(txn["amount"], txn["currency"])
                        lines.append(f"{i}. {emoji} {amount_str} — {cat_emoji} {txn['category']}")
                    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
                else:
                    await callback.message.edit_text(
                        "⚠️ Saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring."
                    )

        logger.info(f"{len(parsed_list)} transaction(s) confirmed and saved for user {pending['telegram_id']}")

    except Exception as e:
        logger.error(f"Confirmation error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"))
async def handle_cancel(callback: CallbackQuery):
    """Cancel transaction(s) - don't save."""
    confirm_key = callback.data.replace("cancel_", "")
    _pending_confirmations.pop(confirm_key, None)

    await callback.message.edit_text("🚫 Operatsiya bekor qilindi.")
    await callback.answer()
    logger.info(f"Transaction cancelled by user {callback.from_user.id}")
