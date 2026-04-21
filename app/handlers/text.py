"""
Text message handler — allows users to type transactions instead of using voice.
Supports multiple transactions in one message separated by commas or conjunctions.
Example: "ovqatga 50 ming, transportga 20 ming" or "maosh oldim 5 million"
"""
import time
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ButtonStyle
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.parser import parse_transactions
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
    """Parse typed text as financial transaction(s). Supports multiple in one message."""
    text = message.text.strip()
    user_id = message.from_user.id

    # Clean up stale confirmations on each message
    _cleanup_stale_pending()

    # Skip very short messages
    if len(text) < 3:
        return

    # Try to parse as transaction(s)
    parsed_list = await parse_transactions(text)

    if not parsed_list:
        # Not a transaction — silently ignore to avoid annoying the user
        return

    # Store pending confirmation with all parsed results
    confirm_key = f"txt_{user_id}_{message.message_id}"
    _text_pending[confirm_key] = {
        "telegram_id": user_id,
        "first_name": message.from_user.first_name,
        "username": message.from_user.username,
        "text": text,
        "parsed_list": parsed_list,
        "created_at": time.time(),
    }

    # Build confirmation message
    confirm_text = _build_confirm_text(parsed_list, text)

    btn_label = "✅ Ha, barchasini saqlash" if len(parsed_list) > 1 else "✅ Ha, saqlash"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=btn_label, callback_data=f"txtconf_{confirm_key}", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton(text="❌ Yo'q", callback_data=f"txtcan_{confirm_key}", style=ButtonStyle.DANGER),
        ]
    ])

    await message.answer(confirm_text, parse_mode="Markdown", reply_markup=keyboard)
    logger.info(f"Text parsed for user {user_id}: {len(parsed_list)} txn(s)")


# ── Confirmation message builder ─────────────────────────────

def _build_confirm_text(parsed_list: list, raw_text: str) -> str:
    """Build a confirmation message for one or more parsed transactions."""
    if len(parsed_list) == 1:
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
            f"📝 _{raw_text}_\n\n"
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
    lines.append("\nBarchasini saqlaymizmi?")
    return "\n".join(lines)


# ── Confirmation callbacks ───────────────────────────────────

@router.callback_query(F.data.startswith("txtconf_"))
async def handle_text_confirm(callback: CallbackQuery):
    """Save all text-based transactions after confirmation."""
    confirm_key = callback.data.replace("txtconf_", "")
    pending = _text_pending.pop(confirm_key, None)

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

        logger.info(f"{len(parsed_list)} text transaction(s) saved for user {pending['telegram_id']}")

    except Exception as e:
        logger.error(f"Text confirmation error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

    await callback.answer()


@router.callback_query(F.data.startswith("txtcan_"))
async def handle_text_cancel(callback: CallbackQuery):
    """Cancel text-based transaction(s)."""
    confirm_key = callback.data.replace("txtcan_", "")
    _text_pending.pop(confirm_key, None)

    await callback.message.edit_text("🚫 Operatsiya bekor qilindi.")
    await callback.answer()
    logger.info(f"Text transaction cancelled by user {callback.from_user.id}")
