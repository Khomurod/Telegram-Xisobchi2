import os
import time
from collections import defaultdict
from aiogram import Router, types, F, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ButtonStyle
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.speech_service import transcribe_audio, clean_transcript
from app.services.parser import parse_transaction
from app.services.transaction import TransactionService
from app.config import settings
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("voice_handler")
router = Router()

# Ensure temp directory exists
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

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
    processing_msg = await message.answer("🎤 Ovozli xabar qabul qilindi. Qayta ishlanmoqda...")

    try:
        # Step 2: Download voice file
        file = await bot.get_file(message.voice.file_id)
        local_path = os.path.join(TEMP_DIR, f"{message.voice.file_id}.ogg")
        await bot.download_file(file.file_path, destination=local_path)

        try:
            logger.info(f"Downloaded voice to: {local_path}")
            # Step 3: Transcribe with Google Cloud STT
            result = await transcribe_audio(local_path)
        finally:
            # Ensure OGG cleanup even if transcribe_audio doesn't reach its own finally
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass

        if not result.text:
            await processing_msg.edit_text(
                "❌ Ovozli xabaringizni tushunolmadim.\n"
                "Iltimos, aniqroq gapirib, qaytadan yuboring."
            )
            return

        # Step 4: Parse transaction
        parsed = parse_transaction(result.text)

        if not parsed:
            await processing_msg.edit_text(
                "🤔 Summani aniqlay olmadim.\n"
                "Iltimos, aniqroq ayting. Masalan:\n"
                "\"Ovqatga 50 ming so'm sarfladim\""
            )
            return

        # Step 5: Ask for confirmation
        type_uz = "Kirim" if parsed.type == "income" else "Chiqim"
        emoji = "📈" if parsed.type == "income" else "📉"
        cat_emoji = CATEGORY_EMOJI.get(parsed.category, "📦")
        cat_name = CATEGORY_NAMES.get(parsed.category, parsed.category)
        amount_str = format_amount(parsed.amount, parsed.currency)

        # Store pending confirmation — include the parsed result so confirm
        # handler can use it directly without re-parsing (Fix: double-parsing bug)
        confirm_key = f"{user_id}_{message.message_id}"
        _pending_confirmations[confirm_key] = {
            "telegram_id": user_id,
            "first_name": message.from_user.first_name,
            "username": message.from_user.username,
            "text": result.text,
            "parsed": parsed,
            "confidence": result.confidence,
            "created_at": time.time(),  # TTL timestamp
        }

        # Add confidence warning if transcription quality is low
        conf_warning = ""
        if result.confidence < 0.6:
            conf_warning = "\n⚠️ _Ovoz sifati past. Iltimos, tekshiring._\n"

        # Clean up transcript for display (GPT-4o-mini)
        display_text = await clean_transcript(result.text)

        confirm_text = (
            f"{emoji} *{type_uz}*\n"
            f"💵 {amount_str}\n"
            f"{cat_emoji} {cat_name}\n\n"
            f"📝 _{display_text}_\n"
            f"{conf_warning}\n"
            f"Shu ma'lumot to'g'rimi?"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, saqlash", callback_data=f"confirm_{confirm_key}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=f"cancel_{confirm_key}", style=ButtonStyle.DANGER),
            ]
        ])

        await processing_msg.edit_text(confirm_text, parse_mode="Markdown", reply_markup=keyboard)
        logger.info(f"Confirmation sent to user {user_id} (conf: {result.confidence:.2f})")

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


# ── Confirmation callbacks ───────────────────────────────────

@router.callback_query(F.data.startswith("confirm_"))
async def handle_confirm(callback: CallbackQuery):
    """Save transaction after user confirms — uses pre-parsed result (no re-parsing)."""
    confirm_key = callback.data.replace("confirm_", "")
    pending = _pending_confirmations.pop(confirm_key, None)

    if not pending:
        await callback.answer("Bu operatsiya eskirgan. Qaytadan yuboring.", show_alert=True)
        return

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            txn_repo = TransactionRepository(session)
            service = TransactionService(user_repo, txn_repo)

            # Use save_parsed() — the parsed result is what the user already approved,
            # so we store exactly that rather than re-parsing the raw text.
            result = await service.save_parsed(
                telegram_id=pending["telegram_id"],
                parsed=pending["parsed"],
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
            logger.info(f"Transaction confirmed and saved for user {pending['telegram_id']}")
        else:
            await callback.message.edit_text(
                "⚠️ Saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring."
            )

    except Exception as e:
        logger.error(f"Confirmation error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"))
async def handle_cancel(callback: CallbackQuery):
    """Cancel transaction - don't save."""
    confirm_key = callback.data.replace("cancel_", "")
    _pending_confirmations.pop(confirm_key, None)

    await callback.message.edit_text("🚫 Operatsiya bekor qilindi.")
    await callback.answer()
    logger.info(f"Transaction cancelled by user {callback.from_user.id}")
