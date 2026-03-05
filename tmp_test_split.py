"""Standalone test for parse_transactions splitting logic."""
import sys
import re
from dataclasses import dataclass
from typing import Optional

# Inline the split pattern and test it directly (no app imports needed)
_SPLIT_PATTERN = re.compile(
    r'\s*[,;]\s*'
    r'|\s+(?:va|ham|yana|keyin|undan keyin|so\'ngra)\s+'
    r'|\s+(?:и|а также|потом|ещё)\s+',
    re.IGNORECASE,
)

def _split_into_fragments(text: str) -> list[str]:
    parts = _SPLIT_PATTERN.split(text)
    return [p.strip() for p in parts if p and p.strip()]


# Test cases
tests = [
    ("ovqatga 50 ming, transportga 20 ming", 2),
    ("ovqatga 50 ming va transportga 20 ming", 2),
    ("dori 15 ming, transport 20 ming va ovqat 50 ming", 3),
    ("ovqatga 50 ming", 1),
    ("ovqatga 50 ming; transport 20 ming", 2),
    ("ovqatga 50 ming ham transport 20 ming", 2),
    ("ovqatga 50 ming yana dori 15 ming", 2),
    ("salom dunyo", 1),  # no split points = single fragment
    ("", 0),
]

print("=" * 60)
print("Testing _split_into_fragments()")
print("=" * 60)
passed = 0
failed = 0
for text, expected_count in tests:
    fragments = _split_into_fragments(text)
    status = "✅" if len(fragments) == expected_count else "❌"
    if status == "✅":
        passed += 1
    else:
        failed += 1
    print(f"{status}  '{text}'")
    print(f"    Expected {expected_count} fragment(s), got {len(fragments)}: {fragments}")
    
print(f"\n{'=' * 60}")
print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
print(f"{'=' * 60}")

sys.exit(1 if failed > 0 else 0)
