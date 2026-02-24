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
    demo_mode = State()  # Test message — parsed but NOT saved


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
        [
            KeyboardButton(text="❓ Yordam"),
            KeyboardButton(text="🤝 Tavsiya", style=ButtonStyle.SUCCESS),
        ],
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
    """Show demo invite after walkthrough is done."""
    name = message.from_user.first_name or "do'stim"
    await state.set_state(Onboarding.demo_mode)

    await message.answer(
        f"🎉 *Ajoyib, {name}! Siz tayyor!*\n\n"
        "🧪 *Sinab ko'ramizmi?*\n\n"
        "Menga bitta ovozli yoki matnli xabar yuboring — "
        "masalan, bugun qilgan xarajatingizni ayting.\n\n"
        "⚠️ *Bu faqat sinov — hech narsa saqlanmaydi!*\n"
        "Natijani ko'rsataman, keyin asosiy rejimga o'tamiz. 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    logger.info(f"User {message.from_user.id} entered demo mode")


async def _show_main_keyboard(message: Message, state: FSMContext):
    """Clear FSM and show main keyboard — onboarding complete."""
    await state.clear()
    name = message.from_user.first_name or "do'stim"
    await message.answer(
        f"🚀 *Zo'r, {name}! Endi asosiy rejimga o'tamiz.*\n\n"
        "Endi istalgan vaqt ovozli yoki matnli xabar yuboring — "
        "men hisobga olaman. 📊",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    logger.info(f"User {message.from_user.id} completed full onboarding")


# ── Demo mode: parse but do NOT save ─────────────────────────────

@router.message(Onboarding.demo_mode, F.text)
async def demo_text(message: Message, state: FSMContext):
    """Parse user text in demo mode — show result but don't save."""
    from app.services.parser import parse_transaction
    raw = message.text.strip()
    parsed = parse_transaction(raw)
    await _show_demo_result(message, state, parsed, raw)


@router.message(Onboarding.demo_mode, F.voice)
async def demo_voice(message: Message, state: FSMContext):
    """Transcribe and parse voice in demo mode — show result but don't save."""
    from aiogram import Bot
    from app.services.speech_service import transcribe_audio
    from app.services.parser import parse_transaction
    import tempfile, os

    await message.answer("⏳ Ovozingizni tahlil qilyapman...⁠🔊")

    bot: Bot = message.bot
    file = await bot.get_file(message.voice.file_id)
    suffix = ".ogg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name

    try:
        await bot.download_file(file.file_path, destination=tmp_path)
        result = await transcribe_audio(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if not result.text:
        await message.answer(
            "⚠️ Ovozni tushunmadim. Iltimos, matn yuboring yoki qayta urinib ko'ring."
        )
        return

    await message.answer(f"📝 *Eshitildi:* _{result.text}_", parse_mode="Markdown")
    parsed = parse_transaction(result.text)
    await _show_demo_result(message, state, parsed, result.text)


async def _show_demo_result(message: Message, state: FSMContext, parsed, raw: str):
    """Show what the bot understood from the demo message, then switch to main keyboard."""
    from app.utils.formatting import format_amount
    from app.constants import CATEGORY_EMOJI

    if not parsed or not parsed.amount:
        await message.answer(
            "🤔 *Tushunmadim...*\n\n"
            f"_\"{raw}\"_ dan ma'lumot ajrata olmadim.\n"
            "Haqiqiy rejimda yozayotganda aniqroq yozing, masalan:\n"
            '📌 _"Ovqatga 50 ming so\'m sarfladim"_',
            parse_mode="Markdown",
        )
    else:
        type_uz = "Kirim 📈" if parsed.type == "income" else "Chiqim 📉"
        cat = parsed.category or "boshqa"
        cat_emoji = CATEGORY_EMOJI.get(cat, "📦")
        amount_str = format_amount(parsed.amount, parsed.currency or "UZS")
        desc = parsed.description or raw

        await message.answer(
            "🧪 *Bot nima tushundi? (SINOV)*\n\n"
            f"✨ Tur: *{type_uz}*\n"
            f"💵 Summa: *{amount_str}*\n"
            f"{cat_emoji} Kategoriya: *{cat}*\n"
            f"💬 Tavsif: _{desc}_\n\n"
            "⚠️ *Bu faqat sinov edi — hech narsa saqlanmadi!*\n"
            "Haqiqiy rejimda xuddi shunday ishlaydi. 👇",
            parse_mode="Markdown",
        )

    await asyncio.sleep(1)
    await _show_main_keyboard(message, state)

