"""
Shared constants used across the application.
Centralizes timezone, category names, and emoji mappings.
"""
from datetime import timezone, timedelta, date

# Uzbekistan timezone (UTC+5)
UZT = timezone(timedelta(hours=5))

# Category emoji mappings
CATEGORY_EMOJI = {
    "oziq-ovqat": "🍽", "transport": "🚕", "uy-joy": "🏠",
    "sog'liq": "💊", "kiyim": "👔", "aloqa": "📱",
    "ta'lim": "📚", "ko'ngil ochar": "🎬", "o'tkazma": "💸",
    "maosh": "💰", "boshqa": "📦",
}

# Category display names in Uzbek
CATEGORY_NAMES = {
    "oziq-ovqat": "Oziq-ovqat", "transport": "Transport", "uy-joy": "Uy-joy",
    "sog'liq": "Sog'liq", "kiyim": "Kiyim", "aloqa": "Aloqa",
    "ta'lim": "Ta'lim", "ko'ngil ochar": "Ko'ngil ochar",
    "o'tkazma": "O'tkazma", "maosh": "Maosh", "boshqa": "Boshqa",
}

# Category display names with emoji (for reports)
CATEGORY_DISPLAY = {
    cat: f"{CATEGORY_EMOJI.get(cat, '📦')} {name}"
    for cat, name in CATEGORY_NAMES.items()
}

# Uzbek month names (for reports — %B gives English, this gives Uzbek)
MONTH_NAMES_UZ = {
    1: "Yanvar", 2: "Fevral", 3: "Mart",
    4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr",
    10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}


def uzbek_month_year(dt) -> str:
    """Return month/year string in Uzbek, e.g. 'Fevral 2026'."""
    return f"{MONTH_NAMES_UZ[dt.month]} {dt.year}"


# ── Uzbekistan cities (for Ramadan feature — Aladhan API) ────

UZBEKISTAN_CITIES = {
    "Tashkent": "Toshkent",
    "Samarkand": "Samarqand",
    "Bukhara": "Buxoro",
    "Namangan": "Namangan",
    "Andijan": "Andijon",
    "Fergana": "Farg'ona",
    "Nukus": "Nukus",
    "Karshi": "Qarshi",
    "Urgench": "Urganch",
    "Jizzakh": "Jizzax",
    "Navoi": "Navoiy",
    "Termez": "Termiz",
    "Gulistan": "Guliston",
    "Kokand": "Qo'qon",
}

# Ramadan 2026 (1447 AH) — generous range to account for moon-sighting
RAMADAN_START = date(2026, 2, 17)
RAMADAN_END = date(2026, 3, 21)

