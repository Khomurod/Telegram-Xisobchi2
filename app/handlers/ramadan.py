"""
Ramadan handler — shows fasting times, duas, and Ramadan info.

Triggered by the 🌙 Ramazon keyboard button.
Supports all Uzbekistan cities — users pick their city on first use,
and the preference is stored in the database.

Designed for future auto-notification support:
  - User city is stored persistently
  - get_fasting_times() returns all data needed for scheduled notifications
"""
import asyncio
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.enums import ButtonStyle
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.services.ramadan import get_fasting_times, get_iftar_countdown, is_ramadan_active
from app.constants import UZBEKISTAN_CITIES
from app.utils.logger import setup_logger

logger = setup_logger("ramadan_handler")
router = Router()


# ── FSM state for city selection ─────────────────────────────
class RamadanSetup(StatesGroup):
    choosing_city = State()


# ── Standard Ramadan Duas ────────────────────────────────────

SAHARLIK_DUA = (
    "📿 *Saharlik (ro'za tutish) duosi:*\n\n"
    '_"Navaytu an asuma savma shahri'
    " Ramadona minal fajri ilal mag'ribi,"
    ' xolisan lillahi ta\'ala"_\n\n'
    "📖 _Ma'nosi: Ramazon oyining ro'zasini "
    "subhdan to kechgacha tutmoqni niyat qildim, "
    "xolis Alloh taolo uchun._"
)

IFTORLIK_DUA = (
    "📿 *Iftorlik (ro'za ochish) duosi:*\n\n"
    '_"Allohumma laka sumtu va bika amantu'
    " va 'alayka tavakkaltu"
    ' va \'ala rizqika aftartu"_\n\n'
    "📖 _Ma'nosi: Ey Alloh, Sen uchun ro'za tutdim, "
    "Senga iymon keltirdim, Senga tavakkal qildim "
    "va bergan rizqing bilan iftor qildim._"
)


# ── 🌙 Ramazon button handler ───────────────────────────────

@router.message(F.text == "🌙 Ramazon")
async def btn_ramazon(message: Message, state: FSMContext):
    """Show Ramadan fasting times for the user's city."""
    if not is_ramadan_active():
        await message.answer(
            "🌙 Ramazon oyi hozircha boshlanmagan yoki tugagan.\n"
            "Keyingi Ramazon oyida qaytadan foydalanishingiz mumkin!"
        )
        return

    # Get the user's saved city
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user or not user.city:
            # No city set — ask user to choose
            await _show_city_picker(message, state)
            return

        # Show fasting times for saved city
        await _show_fasting_times(message, user.city)

    except Exception as e:
        logger.error(f"Ramadan handler error: {e}", exc_info=True)
        await message.answer("⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")


# ── City picker ──────────────────────────────────────────────

async def _show_city_picker(message: Message, state: FSMContext):
    """Show inline buttons for all Uzbekistan cities."""
    rows = []
    cities = list(UZBEKISTAN_CITIES.items())
    for i in range(0, len(cities), 3):
        row = []
        for key, display_name in cities[i:i + 3]:
            row.append(InlineKeyboardButton(
                text=display_name,
                callback_data=f"ramcity_{key}",
            ))
        rows.append(row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(
        "🏙 *Shahringizni tanlang:*\n\n"
        "Saharlik va Iftorlik vaqtlari shahringizga qarab farq qiladi.",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await state.set_state(RamadanSetup.choosing_city)


@router.callback_query(F.data.startswith("ramcity_"))
async def handle_city_selection(callback: CallbackQuery, state: FSMContext):
    """Save the selected city and show fasting times."""
    city_key = callback.data.replace("ramcity_", "")
    display_name = UZBEKISTAN_CITIES.get(city_key)

    if not display_name:
        await callback.answer("Noma'lum shahar.", show_alert=True)
        return

    try:
        # Save city to database
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_city(callback.from_user.id, city_key)

        await callback.answer(f"✅ {display_name} tanlandi!")

        # Edit the city picker message to show confirmation
        await callback.message.edit_text(
            f"✅ Shahringiz: *{display_name}*\n\n"
            "Endi 🌙 Ramazon tugmasini bosing — vaqtlar ko'rsatiladi.",
            parse_mode="Markdown",
        )

        # Immediately show fasting times too
        await _show_fasting_times(callback.message, city_key)

    except Exception as e:
        logger.error(f"City selection error: {e}", exc_info=True)
        await callback.answer("⚠️ Xatolik yuz berdi.", show_alert=True)

    await state.clear()


# ── Fasting times display ────────────────────────────────────

async def _show_fasting_times(message: Message, city_key: str):
    """Fetch and display today's fasting times."""
    display_name = UZBEKISTAN_CITIES.get(city_key, city_key)

    times = await get_fasting_times(city_key)

    if not times:
        await message.answer(
            f"⚠️ {display_name} uchun vaqtlarni olishda xatolik.\n"
            "Iltimos, keyinroq qayta urinib ko'ring."
        )
        return

    # Countdown to iftar
    countdown = get_iftar_countdown(times.maghrib)
    countdown_line = ""
    if countdown:
        countdown_line = f"\n⏳ *Iftorgacha:* {countdown}\n"
    else:
        countdown_line = "\n🎉 *Bugungi iftor vaqti o'tdi!*\n"

    # Ramadan day info
    day_info = ""
    if times.hijri_month == 9:  # Ramadan
        day_info = f"📅 *{times.ramadan_day}-kun* / 30"
    else:
        day_info = "📅 Ramazon"

    text = (
        f"🌙 *Ramazon — {display_name}*\n\n"
        f"{day_info}\n\n"
        f"🍽 *Saharlik tugashi (imsok):* {times.imsak}\n"
        f"🌅 *Bomdod (fajr):* {times.fajr}\n"
        f"☀️ *Quyosh chiqishi:* {times.sunrise}\n\n"
        f"🌆 *Iftorlik (mag'rib):* {times.maghrib}\n"
        f"{countdown_line}\n"
        "─────────────────"
    )

    # Inline buttons for duas and city change
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📿 Duolar",
                callback_data="ram_duas",
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                text="🏙 Shaharni o'zgartirish",
                callback_data="ram_changecity",
                style=ButtonStyle.PRIMARY,
            ),
        ],
    ])

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    logger.info(f"Ramadan times shown for {display_name} (day {times.ramadan_day})")


# ── Duas callback ────────────────────────────────────────────

@router.callback_query(F.data == "ram_duas")
async def handle_duas(callback: CallbackQuery):
    """Show standard Ramadan duas."""
    await callback.answer()

    duas_text = (
        "🌙 *Ramazon Duolari*\n\n"
        "─────────────────\n\n"
        f"{SAHARLIK_DUA}\n\n"
        "─────────────────\n\n"
        f"{IFTORLIK_DUA}"
    )

    await callback.message.answer(duas_text, parse_mode="Markdown")
    logger.info(f"Duas shown for user {callback.from_user.id}")


# ── Change city callback ─────────────────────────────────────

@router.callback_query(F.data == "ram_changecity")
async def handle_change_city(callback: CallbackQuery, state: FSMContext):
    """Re-show the city picker."""
    await callback.answer()
    await _show_city_picker(callback.message, state)
