from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("yandex_gpt")

_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
_PARSER_SYSTEM_PROMPT = (
    "Siz o'zbek tilidagi moliyaviy yordamchisiz. "
    "Foydalanuvchining matnini tahlil qiling va faqatgina qat'iy JSON formatida javob bering. "
    "Hech qanday qo'shimcha izoh yoki matn yozmang.\n\n"
    "Qoidalar:\n"
    "1. 'type': faqat 'income' (kirim/daromad) yoki 'expense' (chiqim/xarajat) bo'lishi shart.\n"
    "2. 'amount': faqat raqam (masalan, 'ellik ming' -> 50000).\n"
    "3. 'currency': faqat 'UZS' yoki 'USD'.\n"
    "4. 'category': faqat quyidagilardan biri bo'lishi shart: oziq-ovqat, transport, uy-joy, "
    "sog'liq, kiyim, aloqa, ta'lim, ko'ngil ochar, o'tkazma, maosh, boshqa.\n"
    "5. 'description': Xarajat yoki daromadning qisqacha mazmuni.\n\n"
    "Agar foydalanuvchi bir nechta operatsiyani bitta xabarda aytgan bo'lsa, JSON array "
    "(ro'yxat) qaytaring."
)
_TRANSACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "amount", "currency", "category", "description"],
    "properties": {
        "type": {"type": "string", "enum": ["income", "expense"]},
        "amount": {"type": "number"},
        "currency": {"type": "string", "enum": ["UZS", "USD"]},
        "category": {
            "type": "string",
            "enum": [
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
            ],
        },
        "description": {"type": "string"},
    },
}
_TRANSACTION_RESPONSE_SCHEMA: dict[str, Any] = {
    "anyOf": [
        _TRANSACTION_SCHEMA,
        {
            "type": "array",
            "minItems": 1,
            "items": _TRANSACTION_SCHEMA,
        },
    ]
}


class YandexGPTError(RuntimeError):
    """Base exception for YandexGPT integration failures."""


class YandexGPTHTTPError(YandexGPTError):
    """Raised when the YandexGPT API returns a non-200 response."""


class YandexGPTClient:
    _session: aiohttp.ClientSession | None = None
    _session_lock = asyncio.Lock()

    def __init__(
        self,
        *,
        api_key: str | None = None,
        folder_id: str | None = None,
        model_uri: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.YANDEX_API_KEY
        self.folder_id = folder_id or settings.YANDEX_FOLDER_ID
        self.model_uri = model_uri or settings.YANDEX_GPT_MODEL_URI
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds or settings.YANDEX_API_TIMEOUT_SECONDS)

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        if not self.api_key:
            raise YandexGPTError("YANDEX_API_KEY is not configured.")
        if not self.folder_id:
            raise YandexGPTError("YANDEX_FOLDER_ID is not configured.")
        if not self.model_uri:
            raise YandexGPTError("YandexGPT model URI could not be built.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "text": system_prompt})
        messages.append({"role": "user", "text": prompt})

        payload: dict[str, Any] = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens),
                "reasoningOptions": {
                    "mode": "DISABLED",
                },
            },
            "messages": messages,
        }
        if json_schema is not None:
            payload["jsonSchema"] = {"schema": json_schema}

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        session = await self._get_session()
        async with session.post(
            _COMPLETION_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        ) as response:
            raw_text = await response.text()
            if response.status != 200:
                raise YandexGPTHTTPError(
                    f"YandexGPT API request failed with status {response.status}: {raw_text[:500]}"
                )

        try:
            body = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise YandexGPTError("YandexGPT returned invalid JSON response metadata.") from exc

        result = body.get("result", body)
        alternatives = result.get("alternatives") or []
        if not alternatives:
            raise YandexGPTError("YandexGPT returned no alternatives.")

        alternative = alternatives[0]
        status = alternative.get("status", "")
        if status not in {"ALTERNATIVE_STATUS_FINAL", "ALTERNATIVE_STATUS_TRUNCATED_FINAL"}:
            raise YandexGPTError(f"Unexpected YandexGPT alternative status: {status or 'unknown'}")

        message = alternative.get("message") or {}
        text = (message.get("text") or "").strip()
        if not text:
            raise YandexGPTError("YandexGPT returned an empty completion.")

        return text

    async def parse_transactions(self, text: str) -> str:
        return await self.generate_text(
            text,
            system_prompt=_PARSER_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=800,
            json_schema=_TRANSACTION_RESPONSE_SCHEMA,
        )

    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        if cls._session is not None and not cls._session.closed:
            return cls._session

        async with cls._session_lock:
            if cls._session is None or cls._session.closed:
                cls._session = aiohttp.ClientSession()

        return cls._session

    @classmethod
    async def close(cls) -> None:
        if cls._session is None or cls._session.closed:
            return

        await cls._session.close()
        cls._session = None


_client: YandexGPTClient | None = None


def get_yandex_gpt_client() -> YandexGPTClient:
    global _client
    if _client is None:
        _client = YandexGPTClient()
    return _client


async def close_yandex_gpt_client() -> None:
    await YandexGPTClient.close()
