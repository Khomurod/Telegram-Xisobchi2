"""
Shared constants used across the application.
Centralizes timezone, category names, and emoji mappings.
"""
from datetime import timezone, timedelta

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
