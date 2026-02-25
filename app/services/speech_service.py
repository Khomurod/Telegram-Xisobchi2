"""
Speech-to-Text service — OpenAI Whisper (async, optimized for speed).

Optimized for minimum latency:
  - AsyncOpenAI client (no thread executor overhead)
  - Accepts in-memory bytes (no disk I/O)
  - Uses 'json' response format (faster than 'verbose_json')
  - Client pre-warmed at import time
"""
import os
import time
from io import BytesIO
from dataclasses import dataclass
from typing import Optional
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("speech")

# ── Transcription result ─────────────────────────────────────

@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    duration_seconds: float
    language: str


# ── OpenAI Whisper (Async, pre-warmed) ───────────────────────

_openai_client = None


def _init_openai_client():
    """Initialize the async OpenAI client. Called at import time."""
    global _openai_client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — speech-to-text will not work")
        return
    from openai import AsyncOpenAI
    _openai_client = AsyncOpenAI(api_key=api_key)
    logger.info("OpenAI Whisper async client initialized (pre-warmed)")


# Pre-warm at import time — eliminates ~500ms first-request penalty
_init_openai_client()


# ── Public async API ─────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> TranscriptionResult:
    """
    Transcribe audio using Whisper API.

    Accepts raw audio bytes (no disk I/O needed).
    Uses AsyncOpenAI for zero thread-executor overhead.
    Uses 'json' format for faster API response than 'verbose_json'.

    Args:
        audio_bytes: Raw audio file content (OGG/OPUS from Telegram)
        filename: Filename hint for the API (helps with format detection)
    """
    if not _openai_client:
        raise RuntimeError(
            "OpenAI API key not configured. Set OPENAI_API_KEY env var."
        )

    start_time = time.time()
    logger.info(f"Transcribing audio ({len(audio_bytes):,} bytes)")

    # Wrap bytes in a file-like object with a name for the API
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename

    response = await _openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="uz",
        response_format="json",
        prompt=(
            "33 minga hot dog oldim. Ovqatga 50 ming so'm sarfladim. "
            "Pizza uchun 40 ming ishlatdim. Taksi 15 ming. "
            "Maosh 5 million so'm oldim. Burger 25 mingga oldim. "
            "Coca cola 8 ming. Transport 10 ming. "
            "Dollar 100 oldim. Benzin 80 ming."
        ),
    )

    elapsed = time.time() - start_time

    text = response.text.strip() if response.text else ""
    confidence = 0.95 if text else 0.0

    logger.info(f"Whisper ({elapsed:.1f}s): {text[:150]}")

    return TranscriptionResult(
        text=text,
        confidence=confidence,
        duration_seconds=elapsed,
        language="uz",
    )
