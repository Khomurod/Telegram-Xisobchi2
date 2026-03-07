"""Standalone test for implicit multi-transaction splitting logic."""
import sys
import re

# ── Inline the relevant constants and functions from parser.py ──

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
    "million": 1_000_000, "mln": 1_000_000,
    "milliard": 1_000_000_000,
}

_UZB_SUFFIXES = ("ga", "a", "ning", "ni", "dan", "da", "lik", "ta")

def _strip_uzbek_suffix(word, lookup=None):
    if lookup is None:
        lookup = MULTIPLIERS
    for suffix in _UZB_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            stripped = word[:-len(suffix)]
            if stripped in lookup:
                return stripped
    return word

_QUANTITY_UNITS = {
    "ta", "dona", "kg", "kilo", "gr", "gramm", "litr", "metr",
    "pors", "quti", "paket", "banka", "butilka",
    "marta", "kun", "oy", "yil", "soat", "daqiqa",
    "kishi", "odam", "xil", "tur",
}

_CURRENCY_TOKENS = {"so'm", "som", "dollar", "usd"}
_HALF_WORD = "yarim"

def _is_amount_token(word):
    if re.fullmatch(r'\d+(?:\.\d+)?', word):
        return True
    if word in NUMBER_WORDS or _strip_uzbek_suffix(word, NUMBER_WORDS) in NUMBER_WORDS:
        return True
    if word in MULTIPLIERS or _strip_uzbek_suffix(word) in MULTIPLIERS:
        return True
    if word in _CURRENCY_TOKENS:
        return True
    if word == _HALF_WORD:
        return True
    return False


def _implicit_split(text):
    tokens = []
    for m in re.finditer(r"\d+(?:\.\d+)?|[a-zA-Z\u0400-\u04FF'`]+", text):
        tokens.append((m.group().lower(), m.start(), m.end()))

    if not tokens:
        return [text] if text.strip() else []

    blocks = []
    i = 0
    while i < len(tokens):
        word = tokens[i][0]
        if _is_amount_token(word):
            block_indices = [i]
            block_start = tokens[i][1]
            block_end = tokens[i][2]
            j = i + 1
            while j < len(tokens) and _is_amount_token(tokens[j][0]):
                block_indices.append(j)
                block_end = tokens[j][2]
                j += 1
            blocks.append((block_indices, block_start, block_end))
            i = j
        else:
            i += 1

    money_blocks = []
    for block_indices, bstart, bend in blocks:
        last_idx = block_indices[-1]
        next_idx = last_idx + 1
        if next_idx < len(tokens) and tokens[next_idx][0] in _QUANTITY_UNITS:
            continue
        money_blocks.append((block_indices, bstart, bend))

    if len(money_blocks) < 2:
        return [text] if text.strip() else []

    first_block_start = money_blocks[0][1]
    text_before_first = text[:first_block_start].strip()
    amount_first = len(text_before_first) == 0

    fragments = []
    for idx, (_, bstart, bend) in enumerate(money_blocks):
        if amount_first:
            frag_start = bstart
            if idx + 1 < len(money_blocks):
                frag_end = money_blocks[idx + 1][1]
            else:
                frag_end = len(text)
        else:
            if idx == 0:
                frag_start = 0
            else:
                frag_start = money_blocks[idx - 1][2]
                while frag_start < len(text) and text[frag_start] == ' ':
                    frag_start += 1
            if idx < len(money_blocks) - 1:
                frag_end = bend
            else:
                frag_end = len(text)

        frag = text[frag_start:frag_end].strip()
        if frag:
            fragments.append(frag)

    return fragments if len(fragments) >= 2 else [text]


# ── Test cases ──

tests = [
    # (input, expected_fragment_count, description)
    ("20 mingga kola 40 mingga fanta 15 mingga non", 3,
     "Amount-first: 3 items with mingga"),
    
    ("20 mingga kola 40 mingga fanta 15 mingga non oldim", 3,
     "Amount-first with trailing verb"),
    
    ("kola 20 ming fanta 40 ming non 15 ming", 3,
     "Item-first: 3 items"),
    
    ("kola 20 ming fanta 40 ming non 15 ming oldim", 3,
     "Item-first with trailing verb"),
    
    ("ovqatga 50 ming", 1,
     "Single transaction = no split"),
    
    ("20 mingga kola", 1,
     "Single amount block = no split"),
    
    ("2 ta non 20 mingga kola 40 mingga fanta", 2,
     "Quantity filter: '2 ta' filtered, remaining 2 amounts split"),
    
    ("ellik mingga ovqat yuz mingga transport", 2,
     "Number words as amounts"),
    
    ("besh ming kola on ming fanta", 2,
     "Number words: besh ming / on ming"),
     
    ("", 0,
     "Empty string"),
     
    ("salom dunyo", 1,
     "No amounts at all"),
]

print("=" * 60)
print("Testing _implicit_split()")
print("=" * 60)
passed = 0
failed = 0

for text, expected_count, desc in tests:
    fragments = _implicit_split(text)
    actual_count = len(fragments)
    status = "PASS" if actual_count == expected_count else "FAIL"
    icon = "✅" if status == "PASS" else "❌"
    
    if status == "PASS":
        passed += 1
    else:
        failed += 1
    
    print(f"\n{icon} {desc}")
    print(f"   Input:    '{text}'")
    print(f"   Expected: {expected_count} fragment(s)")
    print(f"   Got:      {actual_count} fragment(s): {fragments}")

print(f"\n{'=' * 60}")
print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
print(f"{'=' * 60}")

sys.exit(1 if failed > 0 else 0)
