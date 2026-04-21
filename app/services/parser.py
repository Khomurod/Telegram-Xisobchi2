from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from app.services.yandex_gpt import YandexGPTError, get_yandex_gpt_client
from app.utils.logger import setup_logger

logger = setup_logger("parser")

_ALLOWED_TYPES = {"income", "expense"}
_ALLOWED_CURRENCIES = {"UZS", "USD"}
_ALLOWED_CATEGORIES = {
    "oziq-ovqat",
    "transport",
    "uy-joy",
    "sog'liq",
    "kiyim",
    "aloqa",
    "ta'lim",
    "ko'ngil ochar",
    "o'tkazma",
    "maosh",
    "boshqa",
}


@dataclass
class ParsedTransaction:
    type: str
    amount: float
    currency: str
    category: str
    description: str


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _coerce_amount(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Boolean amount is invalid.")
    if isinstance(value, (int, float)):
        amount = float(value)
    elif isinstance(value, str):
        amount = float(value.replace(",", "").strip())
    else:
        raise ValueError(f"Unsupported amount type: {type(value)!r}")

    if amount <= 0:
        raise ValueError("Amount must be positive.")

    return amount


def _to_parsed_transaction(item: Any, raw_text: str) -> ParsedTransaction | None:
    if not isinstance(item, dict):
        logger.warning("Skipping non-dict transaction payload: %r", item)
        return None

    txn_type = str(item.get("type", "")).strip().lower()
    currency = str(item.get("currency", "")).strip().upper()
    category = str(item.get("category", "")).strip()
    description = str(item.get("description") or raw_text).strip()[:500]

    if txn_type not in _ALLOWED_TYPES:
        logger.warning("Skipping transaction with invalid type: %r", txn_type)
        return None
    if currency not in _ALLOWED_CURRENCIES:
        logger.warning("Skipping transaction with invalid currency: %r", currency)
        return None
    if category not in _ALLOWED_CATEGORIES:
        logger.warning("Skipping transaction with invalid category: %r", category)
        return None

    amount = _coerce_amount(item.get("amount"))

    return ParsedTransaction(
        type=txn_type,
        amount=amount,
        currency=currency,
        category=category,
        description=description or raw_text,
    )


async def parse_transactions(text: str) -> list[ParsedTransaction]:
    """Parse text that may contain one or more transactions via YandexGPT."""
    normalized = _normalize_text(text)
    if len(normalized) < 3:
        return []

    client = get_yandex_gpt_client()

    try:
        raw_json = await client.parse_transactions(normalized)
        payload = json.loads(raw_json)
        raw_transactions = payload if isinstance(payload, list) else [payload]

        results = []
        for item in raw_transactions:
            parsed = _to_parsed_transaction(item, normalized)
            if parsed is not None:
                results.append(parsed)

        logger.info("parse_transactions -> %s transaction(s)", len(results))
        return results
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        YandexGPTError,
    ):
        logger.error("YandexGPT transaction parsing failed.", exc_info=True)
        return []


async def parse_transaction(text: str) -> ParsedTransaction | None:
    """Parse a single transaction from text and return the first match."""
    results = await parse_transactions(text)
    return results[0] if results else None
