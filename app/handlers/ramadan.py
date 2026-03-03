"""
Ramadan handler — shows fasting times, duas, and Ramadan info.

Triggered by the 🌙 Ramazon keyboard button or /ramazon command.
Supports all Uzbekistan cities — users pick their city on first use,
and the preference is stored in the database.

Designed for future auto-notification support:
  - User city is stored persistently
  - get_fasting_times() returns all data needed for scheduled notifications
"""
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.services.ramadan import get_fasting_times, get_iftar_countdown, is_ramadan_active
from app.constants import UZBEKISTAN_CITIES, UZT, MONTH_NAMES_UZ
from app.utils.logger import setup_logger

logger = setup_logger("ramadan_handler")
router = Router()


# ── FSM state for city selection ─────────────────────────────
class RamadanSetup(StatesGroup):
    choosing_city = State()


# ── Standard Ramadan Duas ────────────────────────────────────

SAHARLIK_DUA = (
    "📿 *Saharlik (ro\u2019za tutish) duosi:*\n\n"
    "\"Navaytu an asuma savma shahri "
    "Ramadona minal fajri ilal mag\u2019ribi, "
    "xolisan lillahi ta\u2019ala\"\n\n"
    "📖 Ma\u2019nosi: Ramazon oyining ro\u2019zasini "
    "subhdan to kechgacha tutmoqni niyat qildim, "
    "xolis Alloh taolo uchun."
)

IFTORLIK_DUA = (
    "📿 *Iftorlik (ro\u2019za ochish) duosi:*\n\n"
    "\"Allohumma laka sumtu va bika amantu "
    "va \u02bcalayka tavakkaltu "
    "va \u02bcala rizqika aftartu, "
    "fag\u02bcfirli ya G\u02bcoffaru ma qoddamtu "
    "va ma axxortu.\"\n\n"
    "📖 Ma\u02bcnosi: Ey Alloh, ushbu ro\u02bczamni Sen uchun tutdim "
    "va Senga iymon keltirdim va Senga tavakkal qildim "
    "va bergan rizqing bilan iftor qildim. "
    "Ey gunohlarni afv qiluvchi Zot, "
    "mening avvalgi va keyingi gunohlarimni mag\u02bcfirat qilgil."
)


# ── 🌙 Ramazon button + /ramazon command ────────────────────

@router.message(F.text == "🌙 Ramazon")
@router.message(Command("ramazon"))
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

        # Show fasting times for saved city (today)
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
        "Saharlik va Iftorlik vaqtlari shahringizga qarab farq qiladi.\n\n"
        "📍 Agar shahringiz ro\u2019yxatda yo\u2019q bo\u2019lsa, "
        "Fatvo Markazi rasmiy botidan foydalaning:\n"
        "👉 @fatvouz\\_taqvim\\_bot",
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
            f"✅ Shahringiz: *{display_name}*",
            parse_mode="Markdown",
        )

        # Immediately show fasting times too
        await _show_fasting_times(callback.message, city_key)

    except Exception as e:
        logger.error(f"City selection error: {e}", exc_info=True)
        await callback.answer("⚠️ Xatolik yuz berdi.", show_alert=True)

    await state.clear()


# ── Fasting times display ────────────────────────────────────

async def _show_fasting_times(message: Message, city_key: str, tomorrow: bool = False):
    """Fetch and display fasting times (today or tomorrow)."""
    display_name = UZBEKISTAN_CITIES.get(city_key, city_key)

    # Determine target date
    target_date = None
    if tomorrow:
        target_date = (datetime.now(UZT) + timedelta(days=1)).date()

    times = await get_fasting_times(city_key, target_date=target_date)

    if not times:
        await message.answer(
            f"⚠️ {display_name} uchun vaqtlarni olishda xatolik.\n"
            "Iltimos, keyinroq qayta urinib ko'ring."
        )
        return

    # Header — today vs tomorrow
    if tomorrow:
        header = f"📅 *Ertaga — {display_name}*"
        countdown_line = ""  # No countdown for tomorrow
    else:
        header = f"🌙 *Ramazon — {display_name}*"
        # Countdown to iftar (only for today)
        countdown = get_iftar_countdown(times.maghrib)
        if countdown:
            countdown_line = f"\n⏳ *Iftorgacha:* {countdown}\n"
        else:
            countdown_line = "\n🎉 *Bugungi iftor vaqti o\u2019tdi!*\n"

    # Build date strings
    display_date = target_date or datetime.now(UZT).date()
    gregorian_str = f"{display_date.day}-{MONTH_NAMES_UZ[display_date.month]} {display_date.year}"
    hijri_str = "Ramazon 1447 h."

    # Ramadan day info + dates
    if times.hijri_month == 9:  # Ramadan
        day_info = (
            f"📅 *{times.ramadan_day}-kun* / 30\n"
            f"🗓 {gregorian_str}  \u2022  {hijri_str}"
        )
    else:
        day_info = "📅 Ramazon"

    text = (
        f"{header}\n\n"
        f"{day_info}\n\n"
        f"🍽 *Saharlik tugashi (imsok):* {times.imsak}\n\n"
        f"🌆 *Iftorlik (mag\u2019rib):* {times.maghrib}\n"
        f"{countdown_line}\n"
        "─────────────────"
    )

    # Build inline buttons
    buttons = []
    if tomorrow:
        # On tomorrow view: show "Back to today" button
        buttons.append(InlineKeyboardButton(
            text="⬅️ Bugun",
            callback_data=f"ram_today_{city_key}",
        ))
    else:
        # On today view: show "Tomorrow" button
        buttons.append(InlineKeyboardButton(
            text="📅 Ertaga",
            callback_data=f"ram_tomorrow_{city_key}",
        ))

    buttons.append(InlineKeyboardButton(
        text="📿 Duolar",
        callback_data="ram_duas",
    ))
    buttons.append(InlineKeyboardButton(
        text="🏙 Shahar",
        callback_data="ram_changecity",
    ))

    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    label = "tomorrow" if tomorrow else "today"
    logger.info(f"Ramadan times ({label}) shown for {display_name} (day {times.ramadan_day})")


# ── Tomorrow / Today callbacks ───────────────────────────────

@router.callback_query(F.data.startswith("ram_tomorrow_"))
async def handle_tomorrow(callback: CallbackQuery):
    """Show tomorrow's fasting times."""
    city_key = callback.data.replace("ram_tomorrow_", "")
    await callback.answer()
    await _show_fasting_times(callback.message, city_key, tomorrow=True)


@router.callback_query(F.data.startswith("ram_today_"))
async def handle_today(callback: CallbackQuery):
    """Switch back to today's fasting times."""
    city_key = callback.data.replace("ram_today_", "")
    await callback.answer()
    await _show_fasting_times(callback.message, city_key, tomorrow=False)


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
