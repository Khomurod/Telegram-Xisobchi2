"""
Simplified onboarding + delayed phone collection handlers.

/start:
- Brief hint + single "Boshlash" button.
- "Boshlash" asks for the user's name (if missing) and enters main flow.

Phone number:
- Not asked during onboarding.
- Collected later (after the 10th transaction prompt) via contact button with skip option.
"""

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.database.connection import async_session
from app.database.repositories.transaction import TransactionRepository
from app.database.repositories.user import UserRepository
from app.services.phone_prompt import (
    PHONE_SKIP_TEXT,
    PHONE_SKIPPED_VALUE,
)
from app.utils.logger import setup_logger

logger = setup_logger("onboarding")
router = Router()


class Onboarding(StatesGroup):
    waiting_name = State()


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="💰 Balans", style=ButtonStyle.PRIMARY),
            KeyboardButton(text="📊 Hisobot", style=ButtonStyle.SUCCESS),
        ],
        [
            KeyboardButton(text="📅 Bugun", style=ButtonStyle.PRIMARY),
            KeyboardButton(text="📅 Hafta", style=ButtonStyle.SUCCESS),
        ],
        [
            KeyboardButton(text="✏️ Tarix", style=ButtonStyle.PRIMARY),
            KeyboardButton(text="📤 Export", style=ButtonStyle.SUCCESS),
        ],
        [
            KeyboardButton(text="❓ Yordam"),
            KeyboardButton(text="🤝 Tavsiya"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Yozing yoki tugmani bosing...",
)


START_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Boshlash", style=ButtonStyle.SUCCESS)]],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Boshlash tugmasini bosing",
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Always show the new minimal intro and keep Telegram profile data fresh."""
    await state.clear()

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )

        await message.answer(
            "Ovoz habar yoki matn yuboring va o'z harajatlaringizni boshqaring",
            reply_markup=START_KEYBOARD,
        )
        logger.info(f"/start shown for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /start: {e}", exc_info=True)
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(F.text == "Boshlash")
async def onboarding_begin(message: Message, state: FSMContext):
    """On start button click: ask for name if missing, else open main keyboard."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )

        if user.first_name:
            await state.clear()
            await message.answer(
                f"Xush kelibsiz, {user.first_name}!\n"
                "Davom etish uchun ovozli yoki matnli xabar yuboring.",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        await message.answer(
            "Ismingizni yozing:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(Onboarding.waiting_name)
        logger.info(f"User {message.from_user.id} entered waiting_name state")
    except Exception as e:
        logger.error(f"Error in onboarding_begin: {e}", exc_info=True)
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Onboarding.waiting_name, F.text)
async def onboarding_name(message: Message, state: FSMContext):
    """Save user-entered name and complete onboarding immediately."""
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Iltimos, haqiqiy ismingizni kiriting (2-50 belgi):")
        return
    if any(ch.isdigit() for ch in name) or not any(ch.isalpha() for ch in name):
        await message.answer("Iltimos, ismingizni faqat harflar bilan kiriting.")
        return

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_name(message.from_user.id, name)
            # Keep Telegram username synchronized in the background.
            await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )

        await state.clear()
        await message.answer(
            f"Rahmat, {name}! Endi boshlashingiz mumkin.",
            reply_markup=MAIN_KEYBOARD,
        )
        logger.info(f"Onboarding completed for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error saving onboarding name: {e}", exc_info=True)
        await message.answer("Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")


@router.message(Onboarding.waiting_name)
async def onboarding_name_fallback(message: Message):
    await message.answer("Iltimos, ismingizni matn ko'rinishida yuboring.")


async def _phone_collection_context(telegram_id: int) -> tuple[bool, str | None]:
    """
    Return (allowed, current_phone).
    Allowed means user reached delayed prompt milestone and may share/skip phone.
    """
    async with async_session() as session:
        user_repo = UserRepository(session)
        txn_repo = TransactionRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return False, None

        txn_count = await txn_repo.count_all(user.id)
        is_allowed = txn_count >= 10
        return is_allowed, user.phone_number


@router.message(F.contact)
async def delayed_phone_contact(message: Message):
    """Handle contact sharing after delayed phone prompt."""
    try:
        allowed, current_phone = await _phone_collection_context(message.from_user.id)
        if not allowed:
            return

        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.answer("Iltimos, o'zingizning telefon raqamingizni yuboring.")
            return

        # Allow replacing skipped value with a real phone.
        if current_phone and current_phone != PHONE_SKIPPED_VALUE:
            await message.answer("Telefon raqamingiz allaqachon saqlangan.", reply_markup=MAIN_KEYBOARD)
            return

        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_phone(message.from_user.id, message.contact.phone_number)

        await message.answer(
            "Rahmat! Telefon raqamingiz saqlandi. Endi yangilanishlarni birinchi bo'lib olasiz.",
            reply_markup=MAIN_KEYBOARD,
        )
        logger.info(f"Phone saved from delayed prompt for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error saving delayed phone contact: {e}", exc_info=True)
        await message.answer("Telefon raqamingizni saqlashda xatolik yuz berdi.")


@router.message(F.text == PHONE_SKIP_TEXT)
async def delayed_phone_skip(message: Message):
    """Allow users to skip delayed phone sharing without blocking the flow."""
    try:
        allowed, current_phone = await _phone_collection_context(message.from_user.id)
        if not allowed:
            return

        if current_phone and current_phone != PHONE_SKIPPED_VALUE:
            await message.answer("Telefon raqamingiz allaqachon saqlangan.", reply_markup=MAIN_KEYBOARD)
            return

        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_phone(message.from_user.id, PHONE_SKIPPED_VALUE)

        await message.answer(
            "Mayli, o'tkazib yuborildi. Xohlasangiz keyinroq ham ulashishingiz mumkin.",
            reply_markup=MAIN_KEYBOARD,
        )
        logger.info(f"Delayed phone share skipped by user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error skipping delayed phone prompt: {e}", exc_info=True)
        await message.answer("Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


__all__ = ["router", "MAIN_KEYBOARD"]
