"""
Uzbek / Russian rule-based financial text parser.

Extracts transaction type (income/expense), amount, currency,
and category from natural language text. Handles:
  - Common Uzbek financial phrases
  - Mixed Uzbek-Russian speech
  - Number words (ellik ming = 50,000)
  - Informal speech patterns
"""
import re
from dataclasses import dataclass
from typing import Optional
from app.utils.logger import setup_logger

logger = setup_logger("parser")


# ── Text normalization for Whisper output ────────────────────

# Common Whisper misrecognitions of Uzbek text
_NORMALIZE_MAP = {
    # Turkish/foreign characters Whisper sometimes outputs for Uzbek
    "ş": "sh", "ç": "ch", "ö": "o'", "ü": "u'",
    "ğ": "g'", "ı": "i", "â": "a",
    # Common Whisper misrecognitions of Uzbek words
    "owqat": "ovqat", "ovkat": "ovqat", "oqat": "ovqat",
    "sarfladam": "sarfladim", "sarflaam": "sarfladim",
    "toladim": "to'ladim", "toladi": "to'ladi",
    "berdm": "berdim",
    "oldm": "oldim",
    "binzin": "benzin",
    # Common spelling variants (multi-char safe — no substring risk)
    "sohm": "so'm", "soum": "so'm",
}

# Regex-based normalization for words that need word-boundary awareness
_NORMALIZE_REGEX = [
    # "min" / "mng" as standalone word → "ming" (handles start, mid, end of text)
    (re.compile(r'\bmin\b'), 'ming'),
    (re.compile(r'\bmng\b'), 'ming'),
    (re.compile(r'\bsom\b'), "so'm"),     # "som" as standalone word
    (re.compile(r'\bmash\b'), 'maosh'),   # "mash" as standalone word
    # Trailing period from Whisper (single dot, not just ellipsis)
    (re.compile(r'\.$'), ''),
]


def _normalize_text(text: str) -> str:
    """Normalize Whisper output to handle common misrecognitions."""
    text = text.lower().strip()
    # Remove trailing dots/ellipsis from Whisper
    text = re.sub(r'\.{2,}$', '', text).strip()
    # Apply character and word replacements
    for old, new in _NORMALIZE_MAP.items():
        text = text.replace(old, new)
    # Apply regex-based word-boundary replacements (handles start/end of text)
    for pattern, replacement in _NORMALIZE_REGEX:
        text = pattern.sub(replacement, text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


@dataclass
class ParsedTransaction:
    type: str        # "income" or "expense"
    amount: float
    currency: str    # "UZS" or "USD"
    category: str
    description: str


# ── Keyword dictionaries ─────────────────────────────────────

# Compound phrases checked FIRST (order matters!)
EXPENSE_COMPOUNDS = [
    "sotib oldim", "sotib oldi", "sotib olingan",
    "xarid qildim", "xarid qildi", "harid qildim",
    "to'lab berdim", "to'lab berdi",
    "pul berdim", "pul berdi",
]

INCOME_COMPOUNDS = [
    "pul oldim", "pul oldi",
    "pul tushdi", "pul keldi",
    "maosh oldim", "maosh oldi",
    "oylik oldim", "oylik oldi",
    "ish haqi oldim", "ish haqi oldi",
    "qaytarib berdi", "qaytarib oldi",
    "qaytardi", "qaytarildi",
    "topdim", "topdi",
]

EXPENSE_KEYWORDS = [
    "sarfladim", "sarfladi", "sarflanadim", "sarfladam",
    "to'ladim", "to'ladi", "to'lash", "toladim",
    "berdim", "berdi",
    "xarajat", "chiqim",
    "ketdi", "chiqdi",
    "yubordim", "yubordi",
    "harid", "xarid",
    # "oldim" alone = "I bought" (expense)
    # compound income phrases (maosh oldim, pul oldim) checked first
    "oldim", "oldi",
    # Buying/eating/using
    "yedim", "yedi", "ichim", "ichdi",
    "kiyim oldim", "dori oldim",
    # Russian
    "потратил", "потратила", "потратили",
    "заплатил", "заплатила", "заплатили",
    "отдал", "отдала", "отдали",
    "купил", "купила", "купили",
    "расход", "оплатил", "оплатила",
]

INCOME_KEYWORDS = [
    "kirim", "tushum",
    "maosh", "oylik", "ish haqi",  # salary words alone = income
    "tushdi", "keldi",
    "daromad",
    "ishladim", "ishladi",
    "topim", "topdim", "topdi",
    # Russian
    "получил", "получила", "получили",
    "заработал", "заработала", "заработали",
    "доход", "зарплата",
    "пришли", "вернули", "вернул",
]

# Category detection keywords
CATEGORIES = {
    "oziq-ovqat": [
        "ovqat", "owqat", "ovkat", "oqat",
        "taom", "oziq", "restoran", "kafe", "choy", "non",
        "go'sht", "gosh", "gosht", "go'shtga", "goshga", "go'sh",
        "bozor", "bozorlik", "market", "magazin", "supermarket", "dokon",
        "tushlik", "nonushta", "kechki", "sabzavot", "meva", "guruch",
        "yog'", "sut", "kolbasa", "pivo", "ichimlik", "yegulik",
        "yedim", "yedi", "ichim",
        "продукты", "еда", "магазин", "ресторан", "кафе", "обед",
    ],
    "transport": [
        "transport", "taksi", "benzin", "avtobus", "metro", "mashina",
        "yoqilg'i", "taxi", "yol", "yo'l kira",
        "заправка", "такси", "бензин", "транспорт",
    ],
    "uy-joy": [
        "uy", "kvartira", "ijara", "kommunal", "gaz", "suv", "elektr",
        "tok", "uy-joy", "hovli", "ta'mir", "remont", "mebel",
        "аренда", "квартплата", "коммуналка",
    ],
    "sog'liq": [
        "dori", "dorixona", "shifoxona", "vrach", "kasalxona", "doktor",
        "apteka", "tibbiyot", "davolash",
        "больница", "лекарство", "врач", "аптека",
    ],
    "kiyim": [
        "kiyim", "kiyim-kechak", "oyoq kiyim", "ko'ylak", "shim",
        "kurtka", "palto", "tufli", "krossovka",
        "одежда", "обувь",
    ],
    "aloqa": [
        "telefon", "internet", "aloqa", "mobil", "tarif", "balans",
        "связь", "телефон", "интернет",
    ],
    "ta'lim": [
        "ta'lim", "kurs", "kitob", "maktab", "universitet", "o'qish",
        "darslik", "repetitor",
        "учеба", "курс", "книга",
    ],
    "ko'ngil ochar": [
        "kino", "teatr", "dam olish", "sayohat", "park", "muzey",
        "o'yin", "konsert",
        "развлечения", "кино",
    ],
    "o'tkazma": [
        "o'tkazma", "transfer", "jo'natdim", "yubordim", "o'tkazdim",
        "perevod", "перевод",
    ],
    "maosh": [
        "maosh", "oylik", "ish haqi", "avans",
        "зарплата", "оклад", "аванс",
    ],
}

# ── Number words ─────────────────────────────────────────────

NUMBER_WORDS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4,
    "besh": 5, "olti": 6, "yetti": 7, "sakkiz": 8,
    "to'qqiz": 9, "toqqiz": 9,
    "o'n": 10, "on": 10,
    "yigirma": 20, "o'ttiz": 30, "ottiz": 30,
    "qirq": 40, "ellik": 50,
    "oltmish": 60, "yetmish": 70,
    "sakson": 80, "to'qson": 90, "toqson": 90,
    "yuz": 100,
}

MULTIPLIERS = {
    "ming": 1_000, "min": 1_000, "mng": 1_000,
    "million": 1_000_000, "mln": 1_000_000, "миллион": 1_000_000,
    "milliard": 1_000_000_000, "миллиард": 1_000_000_000,
    "тысяча": 1_000, "тысяч": 1_000, "тыс": 1_000,
}

# Common Uzbek case suffixes that may be attached to multiplier words
# e.g. "mingga" (to/for 1000), "mingda" (at 1000), "mingdan" (from 1000)
_UZB_SUFFIXES = ("ga", "a", "ning", "ni", "dan", "da", "lik", "ta")


def _strip_uzbek_suffix(word: str, lookup: dict = None) -> str:
    """Strip common Uzbek case suffixes from a word.
    'mingga' → 'ming', 'milliondan' → 'million', 'yuzga' → 'yuz', etc.
    If lookup dict is provided, checks against that; otherwise checks MULTIPLIERS.
    """
    if lookup is None:
        lookup = MULTIPLIERS
    for suffix in _UZB_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            stripped = word[:-len(suffix)]
            if stripped in lookup:
                return stripped
    return word


# ── Public API ────────────────────────────────────────────────

def parse_transaction(text: str) -> Optional[ParsedTransaction]:
    """Parse Uzbek/Russian financial text into a structured transaction."""
    if not text or len(text.strip()) < 3:
        return None

    text_lower = _normalize_text(text)
    logger.info(f"Parsing: '{text_lower}'")

    # 1. Extract amount (must succeed)
    amount = _extract_amount(text_lower)
    if not amount or amount <= 0:
        logger.warning(f"No amount found in: '{text_lower}'")
        return None

    # 2. Detect type
    txn_type = _detect_type(text_lower)

    # 3. Detect currency
    currency = _detect_currency(text_lower)

    # 4. Detect category
    category = _detect_category(text_lower)

    # If category is "maosh" and type wasn't detected, it's income
    if category == "maosh" and txn_type is None:
        txn_type = "income"

    # Default to expense if type still unknown
    if txn_type is None:
        txn_type = "expense"

    result = ParsedTransaction(
        type=txn_type,
        amount=amount,
        currency=currency,
        category=category,
        description=text.strip(),
    )
    logger.info(f"Parsed → {result.type} | {result.amount:,.0f} {result.currency} | {result.category}")
    return result


# ── Internal helpers ──────────────────────────────────────────

def _detect_type(text: str) -> Optional[str]:
    """Detect income vs expense from keywords."""
    # Check income compounds FIRST — they override bare keywords like 'oldim'
    # e.g. "oylik oldim" must beat "oldim" in EXPENSE_KEYWORDS
    for phrase in INCOME_COMPOUNDS:
        if phrase in text:
            return "income"
    for phrase in EXPENSE_COMPOUNDS:
        if phrase in text:
            return "expense"

    # Then single keywords
    for kw in EXPENSE_KEYWORDS:
        if kw in text:
            return "expense"
    for kw in INCOME_KEYWORDS:
        if kw in text:
            return "income"

    return None


def _extract_amount(text: str) -> Optional[float]:
    """Extract numeric amount from text."""
    text = text.replace(",", "").replace("\u00a0", " ")

    # Special: "bir yarim million" = 1.5M, "bir yarim ming" = 1500, etc.
    for mult_word, mult_val in MULTIPLIERS.items():
        if f"bir yarim {mult_word}" in text:
            return mult_val * 1.5

    # Special: "yarim million" = 500k, "yarim ming" = 500, etc.
    for mult_word, mult_val in MULTIPLIERS.items():
        if f"yarim {mult_word}" in text:
            return mult_val * 0.5

    # Pattern 1: digit + multiplier + optional remainder
    # Handles: "30 ming 600" → 30*1000 + 600 = 30600
    #          "50 ming"     → 50*1000 = 50000
    #          "25 mingga"   → 25*1000 = 25000 (suffixed form)
    _suffix_alt = '(?:' + '|'.join(_UZB_SUFFIXES) + ')?'
    for mult_word, mult_val in MULTIPLIERS.items():
        # Try compound first: "30 ming 600" or "30 mingga 600"
        compound = rf'(\d+(?:\.\d+)?)\s*{re.escape(mult_word)}{_suffix_alt}\s+(\d+(?:\.\d+)?)'
        match = re.search(compound, text)
        if match:
            base = float(match.group(1)) * mult_val
            remainder = float(match.group(2))
            return base + remainder

        # Simple: "50 ming" or "50 mingga"
        simple = rf'(\d+(?:\.\d+)?)\s*{re.escape(mult_word)}{_suffix_alt}(?:\s|$)'
        match = re.search(simple, text)
        if match:
            return float(match.group(1)) * mult_val

    # Pattern 2: Uzbek number words + multiplier ("ellik ming", "besh yuz ming")
    word_amount = _parse_number_words(text)
    if word_amount and word_amount > 0:
        return float(word_amount)

    # Pattern 3: Proper thousands-separated numbers ("20 600", "1 000 000")
    # Only join if groups after first are exactly 3 digits
    thousands_pattern = re.findall(r'\b(\d{1,3}(?:\s\d{3})+)\b', text)
    if thousands_pattern:
        parsed = []
        for n in thousands_pattern:
            clean = n.replace(" ", "")
            try:
                parsed.append(float(clean))
            except ValueError:
                continue
        if parsed:
            return max(parsed)

    # Pattern 4: Plain standalone numbers ("50000", "1500.50", "20", "600")
    numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text)
    if numbers:
        parsed = []
        for n in numbers:
            try:
                parsed.append(float(n))
            except ValueError:
                continue
        if parsed:
            return max(parsed)  # Take the largest number as the amount

    return None


def _parse_number_words(text: str) -> Optional[float]:
    """Parse Uzbek number words into a numeric value.
    Examples: 'ellik ming' → 50000, 'besh yuz' → 500, 'ikki million' → 2000000
    """
    words = text.split()
    total = 0
    current = 0
    found = False

    for word in words:
        # Check for number words (including suffixed forms like "yuzga" → "yuz")
        num_key = word if word in NUMBER_WORDS else _strip_uzbek_suffix(word, NUMBER_WORDS)
        if num_key in NUMBER_WORDS:
            val = NUMBER_WORDS[num_key]
            if val == 100:
                # "besh yuz" → 5 * 100
                current = (current if current > 0 else 1) * 100
            else:
                current += val
            found = True
        elif word in MULTIPLIERS or _strip_uzbek_suffix(word) != word:
            # Handle bare "ming" and suffixed "mingga"/"mingdan" etc.
            mult_key = word if word in MULTIPLIERS else _strip_uzbek_suffix(word)
            if current == 0:
                current = 1
            current *= MULTIPLIERS[mult_key]
            total += current
            current = 0
            found = True
        elif found:
            # Stop when we hit non-number word after finding numbers
            break

    total += current
    return total if found and total > 0 else None


def _detect_currency(text: str) -> str:
    """Detect USD or default to UZS."""
    dollar_hints = [
        "dollar", "dollarni", "dollarga",
        "доллар", "$", "usd", "aqsh",
    ]
    for hint in dollar_hints:
        if hint in text:
            return "USD"
    return "UZS"


# Keywords that are too short for safe substring matching (could match inside
# longer unrelated words, e.g. "uy" inside "buyum"). These use word-start
# boundary \b at the beginning so suffixed forms ("uyga", "gazga") still match.
_SHORT_KW_MIN_LEN = 4  # keywords shorter than this get boundary-checked


def _detect_category(text: str) -> str:
    """Match text against category keyword lists.
    Uses substring matching for longer keywords (naturally handles Uzbek
    suffixed forms like ovqatga, taksiga, restoranda). Short keywords
    (< 4 chars) use word-start boundary to prevent false positives.
    """
    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if len(kw) < _SHORT_KW_MIN_LEN:
                # Short keyword — require word-start boundary
                # \b at start prevents "buyum" matching "uy"
                # No \b at end so "uyga" still matches "uy"
                if re.search(rf'\b{re.escape(kw)}', text):
                    return category
            else:
                # Longer keyword — safe to use substring matching
                if kw in text:
                    return category
    return "boshqa"
