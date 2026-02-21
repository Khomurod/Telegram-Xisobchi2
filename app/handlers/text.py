"""
Text message handler — allows users to type transactions instead of using voice.
Example: "ovqatga 50 ming" or "maosh oldim 5 million"
"""
import time
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.parser import parse_transaction
from app.services.transaction import TransactionService
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("text_handler")
router = Router()

# Shared pending confirmations for text input
_text_pending: dict[str, dict] = {}

_PENDING_TTL = 300.0  # 5 minutes — entries older than this are discarded


def _cleanup_stale_pending() -> None:
    """Remove stale text pending confirmations to prevent memory leaks."""
    now = time.time()
    stale = [k for k, v in _text_pending.items() if now - v.get("created_at", 0) > _PENDING_TTL]
    for k in stale:
        logger.debug(f"Discarding stale text pending: {k}")
        _text_pending.pop(k, None)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    """Parse typed text as a financial transaction."""
    text = message.text.strip()
    user_id = message.from_user.id

    # Clean up stale confirmations on each message
    _cleanup_stale_pending()

    # Skip very short messages
    if len(text) < 3:
        return

    # Try to parse as transaction
    parsed = parse_transaction(text)

    if not parsed:
        # Not a transaction — silently ignore to avoid annoying the user
        return

    # Build confirmation
    type_uz = "Kirim" if parsed.type == "income" else "Chiqim"
    emoji = "📈" if parsed.type == "income" else "📉"
    cat_emoji = CATEGORY_EMOJI.get(parsed.category, "📦")
    cat_name = CATEGORY_NAMES.get(parsed.category, parsed.category)
    amount_str = format_amount(parsed.amount, parsed.currency)

    # Store pending confirmation — include parsed result to avoid re-parsing on confirm
    confirm_key = f"txt_{user_id}_{message.message_id}"
    _text_pending[confirm_key] = {
        "telegram_id": user_id,
        "first_name": message.from_user.first_name,
        "username": message.from_user.username,
        "text": text,
        "parsed": parsed,
        "created_at": time.time(),  # TTL timestamp
    }

    confirm_text = (
        f"{emoji} *{type_uz}*\n"
        f"💵 {amount_str}\n"
        f"{cat_emoji} {cat_name}\n\n"
        f"📝 _{text}_\n\n"
        f"Shu ma'lumot to'g'rimi?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, saqlash", callback_data=f"txtconf_{confirm_key}"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data=f"txtcan_{confirm_key}"),
        ]
    ])

    await message.answer(confirm_text, parse_mode="Markdown", reply_markup=keyboard)
    logger.info(f"Text transaction parsed for user {user_id}: {parsed.type} {parsed.amount} {parsed.currency}")


@router.callback_query(F.data.startswith("txtconf_"))
async def handle_text_confirm(callback: CallbackQuery):
    """Save text-based transaction after confirmation — uses pre-parsed result."""
    confirm_key = callback.data.replace("txtconf_", "")
    pending = _text_pending.pop(confirm_key, None)

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
            logger.info(f"Text transaction saved for user {pending['telegram_id']}")
        else:
            await callback.message.edit_text(
                "⚠️ Saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring."
            )

    except Exception as e:
        logger.error(f"Text confirmation error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

    await callback.answer()


@router.callback_query(F.data.startswith("txtcan_"))
async def handle_text_cancel(callback: CallbackQuery):
    """Cancel text-based transaction."""
    confirm_key = callback.data.replace("txtcan_", "")
    _text_pending.pop(confirm_key, None)

    await callback.message.edit_text("🚫 Operatsiya bekor qilindi.")
    await callback.answer()
    logger.info(f"Text transaction cancelled by user {callback.from_user.id}")
