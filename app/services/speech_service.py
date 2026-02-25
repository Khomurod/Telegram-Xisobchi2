"""
Speech-to-Text service — Yandex SpeechKit (async, native Uzbek support).

Optimized for minimum latency:
  - Async HTTP via aiohttp (no thread executor overhead)
  - Accepts in-memory bytes (no disk I/O)
  - OGG/Opus format (Telegram's native format — no conversion needed)
  - Native Uzbek language support (uz-UZ)
"""
import os
import time
from dataclasses import dataclass
from typing import Optional
import aiohttp
from app.utils.logger import setup_logger

logger = setup_logger("speech")

# ── Transcription result ─────────────────────────────────────

@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    duration_seconds: float
    language: str


# ── Yandex SpeechKit API ─────────────────────────────────────

_YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
_yandex_api_key: Optional[str] = None


def _init_yandex_client():
    """Load Yandex API key from environment. Called at import time."""
    global _yandex_api_key
    _yandex_api_key = os.getenv("YANDEX_API_KEY", "")
    if not _yandex_api_key:
        logger.warning("YANDEX_API_KEY not set — speech-to-text will not work")
    else:
        logger.info("Yandex SpeechKit API key loaded (native Uzbek support)")


# Load at import time
_init_yandex_client()


# ── Public async API ─────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> TranscriptionResult:
    """
    Transcribe audio using Yandex SpeechKit synchronous API.

    Accepts raw audio bytes (no disk I/O needed).
    Uses aiohttp for async HTTP — no thread-executor overhead.
    OGG/Opus is Yandex's default format — zero conversion needed.
    Native Uzbek language support (uz-UZ).

    Args:
        audio_bytes: Raw audio file content (OGG/OPUS from Telegram)
        filename: Filename hint (unused by Yandex, kept for API compatibility)
    """
    if not _yandex_api_key:
        raise RuntimeError(
            "Yandex API key not configured. Set YANDEX_API_KEY env var."
        )

    start_time = time.time()
    logger.info(f"Transcribing audio ({len(audio_bytes):,} bytes) via Yandex SpeechKit")

    params = {
        "lang": "uz-UZ",
        "format": "oggopus",
    }

    headers = {
        "Authorization": f"Api-Key {_yandex_api_key}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _YANDEX_STT_URL,
                params=params,
                headers=headers,
                data=audio_bytes,
            ) as resp:
                elapsed = time.time() - start_time

                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Yandex STT error {resp.status}: {error_text}")
                    return TranscriptionResult(
                        text="",
                        confidence=0.0,
                        duration_seconds=elapsed,
                        language="uz",
                    )

                result = await resp.json()
                text = result.get("result", "").strip()
                confidence = 0.95 if text else 0.0

                logger.info(f"Yandex STT ({elapsed:.1f}s): {text[:150]}")

                return TranscriptionResult(
                    text=text,
                    confidence=confidence,
                    duration_seconds=elapsed,
                    language="uz",
                )

    except aiohttp.ClientError as e:
        elapsed = time.time() - start_time
        logger.error(f"Yandex STT network error ({elapsed:.1f}s): {e}")
        return TranscriptionResult(
            text="",
            confidence=0.0,
            duration_seconds=elapsed,
            language="uz",
        )
