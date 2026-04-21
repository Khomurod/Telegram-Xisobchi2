"""
Speech-to-Text service — Yandex SpeechKit (async, native Uzbek support).

Optimized for minimum latency:
  - Async HTTP via aiohttp
  - Accepts in-memory bytes
  - OGG/Opus format (Telegram's native format)
  - Shared ClientSession to avoid per-request session churn
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import aiohttp

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("speech")

_YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    duration_seconds: float
    language: str


async def _get_session() -> aiohttp.ClientSession:
    global _session

    if _session is not None and not _session.closed:
        return _session

    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession()

    return _session


async def close_speech_session() -> None:
    global _session

    if _session is None or _session.closed:
        return

    await _session.close()
    _session = None


async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> TranscriptionResult:
    """
    Transcribe audio using Yandex SpeechKit.

    Args:
        audio_bytes: Raw audio file content (OGG/OPUS from Telegram)
        filename: Filename hint kept for API compatibility.
    """
    del filename

    if not settings.YANDEX_API_KEY:
        raise RuntimeError(
            "Yandex API key not configured. Set YANDEX_API_KEY env var."
        )

    start_time = time.time()
    logger.info("Transcribing audio (%s bytes) via Yandex SpeechKit", f"{len(audio_bytes):,}")

    params = {
        "lang": "uz-UZ",
        "format": "oggopus",
    }
    headers = {
        "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
    }

    try:
        session = await _get_session()
        async with session.post(
            _YANDEX_STT_URL,
            params=params,
            headers=headers,
            data=audio_bytes,
            timeout=aiohttp.ClientTimeout(total=settings.YANDEX_API_TIMEOUT_SECONDS),
        ) as resp:
            elapsed = time.time() - start_time

            if resp.status != 200:
                error_text = await resp.text()
                logger.error("Yandex STT error %s: %s", resp.status, error_text)
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    duration_seconds=elapsed,
                    language="uz",
                )

            result = await resp.json()
            text = result.get("result", "").strip()
            confidence = 0.95 if text else 0.0

            logger.info("Yandex STT (%.1fs): %s", elapsed, text[:150])

            return TranscriptionResult(
                text=text,
                confidence=confidence,
                duration_seconds=elapsed,
                language="uz",
            )

    except aiohttp.ClientError as exc:
        elapsed = time.time() - start_time
        logger.error("Yandex STT network error (%.1fs): %s", elapsed, exc)
        return TranscriptionResult(
            text="",
            confidence=0.0,
            duration_seconds=elapsed,
            language="uz",
        )
