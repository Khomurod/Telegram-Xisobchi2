"""
Fun multi-step onboarding flow triggered by /start.

New users → welcome → ask name → contact sharing → feature walkthrough → main keyboard.
Returning users → short welcome back + main keyboard.
"""
import asyncio
from aiogram import Router, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.enums import ButtonStyle
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.utils.logger import setup_logger

logger = setup_logger("onboarding")
router = Router()


# ── FSM states ───────────────────────────────────────────────
class Onboarding(StatesGroup):
    waiting_name = State()
    waiting_contact = State()
    walkthrough_step = State()


# ── Main keyboard (imported by commands.py too) ──────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="💰 Balans", style=ButtonStyle.PRIMARY),
            KeyboardButton(text="📊 Hisobot", style=ButtonStyle.PRIMARY),
        ],
        [
            KeyboardButton(text="📅 Bugun", style=ButtonStyle.SUCCESS),
            KeyboardButton(text="📅 Hafta", style=ButtonStyle.SUCCESS),
        ],
        [
            KeyboardButton(text="✏️ Tarix", style=ButtonStyle.PRIMARY),
            KeyboardButton(text="📤 Export", style=ButtonStyle.SUCCESS),
        ],
        [KeyboardButton(text="❓ Yordam")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Yozing yoki tugmani bosing...",
)


# ── Walkthrough messages ─────────────────────────────────────

WALKTHROUGH = [
    # Step 1: What the bot does
    (
        "🤖 *Xisobchi Bot nima qiladi?*\n\n"
        "Men sizning shaxsiy moliyaviy yordamchingizman!\n\n"
        "📌 Ovozli xabar yoki matn yuboring — avtomatik ravishda "
        "kirim yoki chiqimingizni qayd etaman.\n\n"
        "🧠 Sun'iy intellekt orqali gapingizni tushunaman:\n"
        '   _"Ovqatga 50 ming so\'m sarfladim"_\n'
        '   _"Maosh oldim 5 million so\'m"_'
    ),
    # Step 2: Text examples
    (
        "💬 *Matn orqali ham ishlaydi!*\n\n"
        "Shunchaki yozing:\n"
        '   📌 _"transport 20 ming"_ → Chiqim qayd etiladi\n'
        '   📌 _"kirim 3 million maosh"_ → Kirim qayd etiladi\n'
        '   📌 _"1200 dollar oylik oldim"_ → USD kirim\n\n'
        "🎤 Va ovozli xabar ham yuborishingiz mumkin!"
    ),
    # Step 3: Commands
    (
        "📝 *Asosiy buyruqlar:*\n\n"
        "/balans — 💰 Umumiy balans\n"
        "/bugun — 📊 Bugungi operatsiyalar\n"
        "/hafta — 📅 Haftalik hisobot\n"
        "/oy — 📅 Oylik hisobot\n"
        "/hisobot — 📋 To'liq hisobot\n"
        "/tarix — ✏️ Tahrirlash va o'chirish\n"
        "/bekor — ↩️ Oxirgi operatsiyani bekor qilish\n"
        "/export — 📤 CSV fayl eksport\n"
        "/yordam — ❓ Yordam"
    ),
    # Step 4: Category showcase
    (
        "📂 *Kategoriyalar avtomatik aniqlanadi:*\n\n"
        "🍽 Oziq-ovqat | 🚕 Transport | 🏠 Uy-joy\n"
        "💊 Sog'liq | 👔 Kiyim | 📱 Aloqa\n"
        "📚 Ta'lim | 🎬 Ko'ngil ochar | 💸 O'tkazma\n"
        "💰 Maosh | 📦 Boshqa\n\n"
        "Bot gapingizdan kategoriyani avtomatik aniqlaydi! 🧠"
    ),
]


# ── /start command ───────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Entry point. New users → onboarding, returning users → welcome back."""
    await state.clear()  # Clear any leftover FSM state

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )

            is_returning = user.phone_number is not None

        if is_returning:
            # ── Returning user: short welcome ──
            name = message.from_user.first_name or "do'stim"
            await message.answer(
                f"👋 *Qaytganingiz bilan, {name}!*\n\n"
                "Tayyor! Ovozli yoki matnli xabar yuboring — "
                "men hisobga olaman. 📊",
                parse_mode="Markdown",
                reply_markup=MAIN_KEYBOARD,
            )
            logger.info(f"Returning user {message.from_user.id} started the bot")
            return

        # ── New user: start onboarding ──
        await message.answer(
            "👋 *Assalomu alaykum!*\n\n"
            "🎙 *Xisobchi Bot*ga xush kelibsiz!\n\n"
            "Men sizning shaxsiy moliyaviy yordamchingizman — "
            "kirim va chiqimlaringizni avtomatik boshqaruvchi "
            "sun'iy intellekt. 🤖✨",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await asyncio.sleep(1)

        # Ask for name
        await message.answer(
            "😊 *Tanishib olaylik!*\n\n"
            "Ismingizni yozing:",
            parse_mode="Markdown",
        )
        await state.set_state(Onboarding.waiting_name)
        logger.info(f"New user {message.from_user.id} started onboarding")

    except Exception as e:
        logger.error(f"Error in /start onboarding: {e}", exc_info=True)
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


# ── Step 1: Receive name ─────────────────────────────────────

@router.message(Onboarding.waiting_name, F.text)
async def onboarding_name(message: Message, state: FSMContext):
    """Save the name and ask for phone number."""
    name = message.text.strip()

    if len(name) < 2 or len(name) > 50:
        await message.answer("😅 Iltimos, haqiqiy ismingizni kiriting (2–50 belgi):")
        return

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_name(message.from_user.id, name)

        await message.answer(
            f"✅ *Xush kelibsiz, {name}!* 🎉",
            parse_mode="Markdown",
        )
        await asyncio.sleep(0.5)

        # Ask for phone number with dedicated contact button
        contact_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text="📱 Kontakt yuborish",
                    request_contact=True,
                    style=ButtonStyle.PRIMARY,
                )],
                [KeyboardButton(
                    text="⏭ O'tkazib yuborish",
                    style=ButtonStyle.DANGER,
                )],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(
            "📱 *Telefon raqamingizni ulashing*\n\n"
            "Pastdagi tugmani bosing — raqamingiz avtomatik yuboriladi.\n"
            "Bu xavfsiz va faqat sizning hisobingiz uchun saqlanadi. 🔒",
            parse_mode="Markdown",
            reply_markup=contact_kb,
        )
        await state.set_state(Onboarding.waiting_contact)

    except Exception as e:
        logger.error(f"Error saving name: {e}", exc_info=True)
        await message.answer("⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")


# ── Step 2: Receive contact ──────────────────────────────────

@router.message(Onboarding.waiting_contact, F.contact)
async def onboarding_contact(message: Message, state: FSMContext):
    """Save phone number from contact sharing button."""
    phone = message.contact.phone_number

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_phone(message.from_user.id, phone)

        await message.answer(
            "✅ *Ro'yxatdan o'tdingiz!* 🎉\n\n"
            "Keling, botning imkoniyatlarini ko'rib chiqamiz...",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await asyncio.sleep(1)

        # Start walkthrough
        await state.update_data(walkthrough_idx=0)
        await state.set_state(Onboarding.walkthrough_step)
        await _send_walkthrough_step(message, state, 0)

    except Exception as e:
        logger.error(f"Error saving contact: {e}", exc_info=True)
        await message.answer("⚠️ Xatolik yuz berdi.")


@router.message(Onboarding.waiting_contact, F.text == "⏭ O'tkazib yuborish")
async def onboarding_skip_contact(message: Message, state: FSMContext):
    """Skip phone number sharing."""
    try:
        # Still mark as onboarded by setting a placeholder
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_phone(message.from_user.id, "skipped")

        await message.answer(
            "⏭ *O'tkazib yuborildi.* Keling, davom etaylik!",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await asyncio.sleep(0.5)

        # Start walkthrough
        await state.update_data(walkthrough_idx=0)
        await state.set_state(Onboarding.walkthrough_step)
        await _send_walkthrough_step(message, state, 0)

    except Exception as e:
        logger.error(f"Error skipping contact: {e}", exc_info=True)
        await message.answer("⚠️ Xatolik yuz berdi.")


@router.message(Onboarding.waiting_contact, F.text)
async def onboarding_contact_text_fallback(message: Message, state: FSMContext):
    """If user types text instead of sharing contact."""
    await message.answer(
        "📱 Iltimos, pastdagi *\"📱 Kontakt yuborish\"* tugmasini bosing,\n"
        "yoki *\"⏭ O'tkazib yuborish\"* ni tanlang.",
        parse_mode="Markdown",
    )


# ── Step 3: Feature walkthrough ──────────────────────────────

async def _send_walkthrough_step(message: Message, state: FSMContext, idx: int):
    """Send a walkthrough message and the 'Keyingi' button."""
    if idx >= len(WALKTHROUGH):
        # Walkthrough complete!
        await _finish_onboarding(message, state)
        return

    # Navigation buttons
    if idx < len(WALKTHROUGH) - 1:
        # More steps to go
        nav_kb = ReplyKeyboardMarkup(
            keyboard=[[
                KeyboardButton(text="➡️ Keyingi", style=ButtonStyle.PRIMARY),
                KeyboardButton(text="⏭ Tugatish", style=ButtonStyle.SUCCESS),
            ]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    else:
        # Last step
        nav_kb = ReplyKeyboardMarkup(
            keyboard=[[
                KeyboardButton(text="🚀 Boshlash!", style=ButtonStyle.SUCCESS),
            ]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

    step_label = f"_{idx + 1}/{len(WALKTHROUGH)}_"
    await message.answer(
        f"{WALKTHROUGH[idx]}\n\n{step_label}",
        parse_mode="Markdown",
        reply_markup=nav_kb,
    )


@router.message(Onboarding.walkthrough_step, F.text == "➡️ Keyingi")
async def walkthrough_next(message: Message, state: FSMContext):
    """Advance to the next walkthrough step."""
    data = await state.get_data()
    idx = data.get("walkthrough_idx", 0) + 1
    await state.update_data(walkthrough_idx=idx)
    await _send_walkthrough_step(message, state, idx)


@router.message(Onboarding.walkthrough_step, F.text.in_({"⏭ Tugatish", "🚀 Boshlash!"}))
async def walkthrough_finish(message: Message, state: FSMContext):
    """Skip remaining walkthrough or finish."""
    await _finish_onboarding(message, state)


async def _finish_onboarding(message: Message, state: FSMContext):
    """Complete onboarding and show the main keyboard."""
    await state.clear()

    name = message.from_user.first_name or "do'stim"
    await message.answer(
        f"🎉 *Tayyor, {name}!*\n\n"
        "Endi ovozli yoki matnli xabar yuboring — "
        "men avtomatik ravishda kirim yoki chiqimingizni qayd etaman.\n\n"
        '📌 Masalan: _"Taksiga 15,000 so\'m xarajat qildim"_\n\n'
        "Yoki pastdagi tugmalardan foydalaning! 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    logger.info(f"User {message.from_user.id} completed onboarding")
