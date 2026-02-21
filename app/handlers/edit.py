"""
Transaction history viewer with inline edit / delete buttons.

/tarix — shows the last 10 transactions with ✏️ Edit and 🗑 Delete buttons.
Uses Telegram Bot API 9.4 colored buttons (ButtonStyle enum).
"""
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.enums import ButtonStyle
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.constants import CATEGORY_EMOJI, CATEGORY_NAMES
from app.utils.formatting import format_amount
from app.utils.logger import setup_logger

logger = setup_logger("edit_handler")
router = Router()


# ── FSM states for the edit flow ─────────────────────────────
class EditTxn(StatesGroup):
    choose_field = State()
    enter_value = State()


# ── /tarix command ───────────────────────────────────────────

@router.message(Command("tarix"))
async def cmd_history(message: Message):
    """Show last 10 transactions with edit/delete buttons."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )
            txn_repo = TransactionRepository(session)
            txns = await txn_repo.get_by_user(user.id)

        if not txns:
            await message.answer("📭 Hali hech qanday operatsiya yo'q.")
            return

        txns = txns[:10]  # last 10

        lines = ["📜 *Oxirgi operatsiyalar:*\n"]
        buttons_rows = []

        for i, txn in enumerate(txns, 1):
            emoji = "📈" if txn.type == "income" else "📉"
            type_uz = "Kirim" if txn.type == "income" else "Chiqim"
            cat_emoji = CATEGORY_EMOJI.get(txn.category, "📦")
            amount_str = format_amount(float(txn.amount), txn.currency)
            date_str = txn.created_at.strftime("%d.%m %H:%M") if txn.created_at else ""

            lines.append(
                f"*{i}.* {emoji} {type_uz} — {amount_str}\n"
                f"     {cat_emoji} {txn.category}  |  📅 {date_str}"
            )

            # Colored buttons: Edit=Primary (blue), Delete=Danger (red)
            buttons_rows.append([
                InlineKeyboardButton(
                    text=f"✏️ {i}. Tahrirlash",
                    callback_data=f"txedit_{txn.id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🗑 {i}. O'chirish",
                    callback_data=f"txdel_{txn.id}",
                    style=ButtonStyle.DANGER,
                ),
            ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons_rows)
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    except Exception as e:
        logger.error(f"Error in /tarix: {e}", exc_info=True)
        await message.answer("Tizimda xatolik yuz berdi.")


# ── Delete callback ──────────────────────────────────────────

@router.callback_query(F.data.startswith("txdel_"))
async def handle_delete(callback: CallbackQuery):
    """Ask for delete confirmation."""
    txn_id = int(callback.data.replace("txdel_", ""))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Ha, o'chirish",
            callback_data=f"txdelyes_{txn_id}",
            style=ButtonStyle.DANGER,
        ),
        InlineKeyboardButton(
            text="❌ Yo'q",
            callback_data="txdelno",
            style=ButtonStyle.PRIMARY,
        ),
    ]])
    await callback.message.answer(
        f"🗑 #{txn_id} operatsiyani o'chirishni tasdiqlaysizmi?",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("txdelyes_"))
async def handle_delete_confirm(callback: CallbackQuery):
    """Delete the transaction after confirmation."""
    txn_id = int(callback.data.replace("txdelyes_", ""))
    try:
        async with async_session() as session:
            txn_repo = TransactionRepository(session)
            deleted = await txn_repo.delete(txn_id)

        if deleted:
            await callback.message.edit_text("✅ Operatsiya o'chirildi.")
            logger.info(f"Transaction {txn_id} deleted by user {callback.from_user.id}")
        else:
            await callback.message.edit_text("⚠️ Operatsiya topilmadi.")
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi.")
    await callback.answer()


@router.callback_query(F.data == "txdelno")
async def handle_delete_cancel(callback: CallbackQuery):
    """Cancel deletion."""
    await callback.message.edit_text("🚫 O'chirish bekor qilindi.")
    await callback.answer()


# ── Edit callback → choose which field to edit ───────────────

@router.callback_query(F.data.startswith("txedit_"))
async def handle_edit_start(callback: CallbackQuery, state: FSMContext):
    """Show field picker for editing a transaction."""
    txn_id = int(callback.data.replace("txedit_", ""))

    await state.update_data(edit_txn_id=txn_id)
    await state.set_state(EditTxn.choose_field)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💵 Summani o'zgartirish",
                callback_data="txfield_amount",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                text="📂 Kategoriyani o'zgartirish",
                callback_data="txfield_category",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔄 Turni o'zgartirish (Kirim↔Chiqim)",
                callback_data="txfield_type",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data="txfield_cancel",
                style=ButtonStyle.DANGER,
            ),
        ],
    ])
    await callback.message.answer(
        f"✏️ #{txn_id} — Qaysi maydonni o'zgartirmoqchisiz?",
        reply_markup=kb,
    )
    await callback.answer()


# ── Field chosen: type toggle (instant, no text input needed) ─

@router.callback_query(EditTxn.choose_field, F.data == "txfield_type")
async def handle_toggle_type(callback: CallbackQuery, state: FSMContext):
    """Toggle income ↔ expense instantly."""
    data = await state.get_data()
    txn_id = data.get("edit_txn_id")

    try:
        async with async_session() as session:
            txn_repo = TransactionRepository(session)
            txn = await txn_repo.get_by_id(txn_id)
            if not txn:
                await callback.message.edit_text("⚠️ Operatsiya topilmadi.")
                await state.clear()
                await callback.answer()
                return

            new_type = "income" if txn.type == "expense" else "expense"
            await txn_repo.update(txn_id, type=new_type)

        type_uz = "Kirim" if new_type == "income" else "Chiqim"
        emoji = "📈" if new_type == "income" else "📉"
        await callback.message.edit_text(
            f"✅ Tur o'zgartirildi: {emoji} *{type_uz}*",
            parse_mode="Markdown",
        )
        logger.info(f"Txn {txn_id}: type toggled to {new_type}")
    except Exception as e:
        logger.error(f"Toggle type error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi.")

    await state.clear()
    await callback.answer()


# ── Field chosen: amount → ask for new value ─────────────────

@router.callback_query(EditTxn.choose_field, F.data == "txfield_amount")
async def handle_edit_amount(callback: CallbackQuery, state: FSMContext):
    """Prompt user to type the new amount."""
    await state.update_data(edit_field="amount")
    await state.set_state(EditTxn.enter_value)
    await callback.message.edit_text("💵 Yangi summani yozing (masalan: 50000 yoki 50 ming):")
    await callback.answer()


# ── Field chosen: category → show category buttons ───────────

@router.callback_query(EditTxn.choose_field, F.data == "txfield_category")
async def handle_edit_category(callback: CallbackQuery, state: FSMContext):
    """Show category selection buttons."""
    await state.update_data(edit_field="category")

    rows = []
    cats = list(CATEGORY_NAMES.items())
    for i in range(0, len(cats), 2):
        row = []
        for cat_key, cat_name in cats[i:i+2]:
            emoji = CATEGORY_EMOJI.get(cat_key, "📦")
            row.append(InlineKeyboardButton(
                text=f"{emoji} {cat_name}",
                callback_data=f"txcat_{cat_key}",
                style=ButtonStyle.SUCCESS,
            ))
        rows.append(row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text("📂 Yangi kategoriyani tanlang:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("txcat_"))
async def handle_category_picked(callback: CallbackQuery, state: FSMContext):
    """Save the chosen category."""
    cat_key = callback.data.replace("txcat_", "")
    data = await state.get_data()
    txn_id = data.get("edit_txn_id")

    if not txn_id:
        await callback.message.edit_text("⚠️ Sessiya tugagan. /tarix buyrug'ini qayta yuboring.")
        await state.clear()
        await callback.answer()
        return

    try:
        async with async_session() as session:
            txn_repo = TransactionRepository(session)
            await txn_repo.update(txn_id, category=cat_key)

        cat_emoji = CATEGORY_EMOJI.get(cat_key, "📦")
        cat_name = CATEGORY_NAMES.get(cat_key, cat_key)
        await callback.message.edit_text(
            f"✅ Kategoriya o'zgartirildi: {cat_emoji} *{cat_name}*",
            parse_mode="Markdown",
        )
        logger.info(f"Txn {txn_id}: category changed to {cat_key}")
    except Exception as e:
        logger.error(f"Category edit error: {e}", exc_info=True)
        await callback.message.edit_text("⚠️ Xatolik yuz berdi.")

    await state.clear()
    await callback.answer()


# ── Cancel edit flow ─────────────────────────────────────────

@router.callback_query(F.data == "txfield_cancel")
async def handle_edit_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel the edit flow."""
    await state.clear()
    await callback.message.edit_text("🚫 Tahrirlash bekor qilindi.")
    await callback.answer()


# ── Enter value (amount) — free text in FSM state ────────────

@router.message(EditTxn.enter_value, F.text)
async def handle_enter_value(message: Message, state: FSMContext):
    """Receive the new value from the user and save it."""
    data = await state.get_data()
    txn_id = data.get("edit_txn_id")
    field = data.get("edit_field")

    if not txn_id or not field:
        await message.answer("⚠️ Sessiya tugagan. /tarix buyrug'ini qayta yuboring.")
        await state.clear()
        return

    raw = message.text.strip()

    if field == "amount":
        # Parse the amount — support "50 ming", "5 mln", plain numbers
        from app.services.parser import _extract_amount, _normalize_text
        amount = _extract_amount(_normalize_text(raw))
        if not amount or amount <= 0:
            await message.answer("⚠️ Summani to'g'ri kiriting (masalan: 50000 yoki 50 ming).")
            return

        try:
            async with async_session() as session:
                txn_repo = TransactionRepository(session)
                await txn_repo.update(txn_id, amount=amount)

            amount_str = format_amount(amount, "UZS")
            await message.answer(
                f"✅ Summa o'zgartirildi: 💵 *{amount_str}*",
                parse_mode="Markdown",
            )
            logger.info(f"Txn {txn_id}: amount changed to {amount}")
        except Exception as e:
            logger.error(f"Amount edit error: {e}", exc_info=True)
            await message.answer("⚠️ Xatolik yuz berdi.")
    else:
        await message.answer("⚠️ Noma'lum maydon.")

    await state.clear()
