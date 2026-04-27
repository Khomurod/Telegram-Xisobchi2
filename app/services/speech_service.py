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


def _preview_text(text: str, limit: int = 150) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


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
    Transcribe audio using Yandex first, then fall back to Faster-Whisper.

    Args:
        audio_bytes: Raw audio file content (OGG/OPUS from Telegram)
        filename: Filename hint used for multipart uploads.
    """
    if settings.YANDEX_API_KEY:
        yandex_result = await _transcribe_audio_yandex(audio_bytes)
        if yandex_result.text:
            return yandex_result

        logger.warning(
            "Yandex primary returned no text; falling back to Faster-Whisper."
        )
    else:
        logger.warning(
            "YANDEX_API_KEY is not configured; falling back to Faster-Whisper."
        )

    if settings.WHISPER_TEST_TRANSCRIBE_URL:
        whisper_result = await transcribe_audio_whisper_test(
            audio_bytes,
            filename=filename,
        )
        if whisper_result.text:
            return whisper_result

        logger.warning(
            "Whisper backup returned no text after Yandex fallback."
        )

    return TranscriptionResult(
        text="",
        confidence=0.0,
        duration_seconds=0.0,
        language="uz",
    )


async def _transcribe_audio_yandex(audio_bytes: bytes) -> TranscriptionResult:
    """
    Transcribe audio using Yandex SpeechKit.

    Args:
        audio_bytes: Raw audio file content (OGG/OPUS from Telegram)
    """

    if not settings.YANDEX_API_KEY:
        raise RuntimeError("Yandex API key not configured. Set YANDEX_API_KEY env var.")

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


async def transcribe_audio_whisper_test(
    audio_bytes: bytes,
    filename: str = "voice.ogg",
) -> TranscriptionResult:
    """
    Transcribe audio using the external Faster-Whisper endpoint.

    The file is sent as multipart/form-data under the `file` field and expects
    a response shaped like {"text": "..."}.
    """
    if not settings.WHISPER_TEST_TRANSCRIBE_URL:
        raise RuntimeError(
            "Whisper URL not configured. Set WHISPER_TEST_URL env var."
        )

    start_time = time.time()
    logger.info(
        "Transcribing audio (%s bytes) via Faster-Whisper %s",
        f"{len(audio_bytes):,}",
        settings.WHISPER_TEST_TRANSCRIBE_URL,
    )

    form = aiohttp.FormData()
    form.add_field(
        "file",
        audio_bytes,
        filename=filename,
        content_type="audio/ogg",
    )

    try:
        session = await _get_session()
        async with session.post(
            settings.WHISPER_TEST_TRANSCRIBE_URL,
            data=form,
            timeout=aiohttp.ClientTimeout(total=settings.WHISPER_TEST_TIMEOUT_SECONDS),
        ) as resp:
            elapsed = time.time() - start_time

            if resp.status != 200:
                error_text = await resp.text()
                logger.error("Whisper STT error %s: %s", resp.status, error_text)
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    duration_seconds=elapsed,
                    language="uz",
                )

            result = await resp.json(content_type=None)
            text = str(result.get("text", "")).strip()
            confidence = 0.95 if text else 0.0

            logger.info("Whisper STT (%.1fs): %s", elapsed, _preview_text(text))

            return TranscriptionResult(
                text=text,
                confidence=confidence,
                duration_seconds=elapsed,
                language="uz",
            )

    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        elapsed = time.time() - start_time
        logger.error("Whisper STT request failed (%.1fs): %s", elapsed, exc)
        return TranscriptionResult(
            text="",
            confidence=0.0,
            duration_seconds=elapsed,
            language="uz",
        )


def should_run_whisper_shadow_test(telegram_user_id: int) -> bool:
    if not settings.WHISPER_TEST_ENABLED:
        return False

    if not settings.WHISPER_TEST_TRANSCRIBE_URL:
        logger.warning(
            "WHISPER_TEST_ENABLED is true but WHISPER_TEST_URL is not configured."
        )
        return False

    allowed_user_id = settings.WHISPER_TEST_TELEGRAM_ID
    if allowed_user_id and telegram_user_id != allowed_user_id:
        return False

    return True


def schedule_whisper_shadow_log(
    *,
    whisper_task: "asyncio.Task[TranscriptionResult]",
    yandex_result: TranscriptionResult,
    user_id: int,
    message_id: int,
) -> None:
    asyncio.create_task(
        _log_whisper_shadow_result(
            whisper_task=whisper_task,
            yandex_result=yandex_result,
            user_id=user_id,
            message_id=message_id,
        )
    )


async def _log_whisper_shadow_result(
    *,
    whisper_task: "asyncio.Task[TranscriptionResult]",
    yandex_result: TranscriptionResult,
    user_id: int,
    message_id: int,
) -> None:
    try:
        whisper_result = await whisper_task
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.error(
            "Whisper shadow task failed for user=%s message=%s: %s",
            user_id,
            message_id,
            exc,
            exc_info=True,
        )
        return

    logger.info(
        (
            "STT shadow compare | user=%s | message=%s | "
            "yandex=%.2fs | whisper=%.2fs | delta=%.2fs"
        ),
        user_id,
        message_id,
        yandex_result.duration_seconds,
        whisper_result.duration_seconds,
        whisper_result.duration_seconds - yandex_result.duration_seconds,
    )
    logger.info(
        'STT shadow texts | user=%s | message=%s | yandex="%s" | whisper="%s"',
        user_id,
        message_id,
        _preview_text(yandex_result.text),
        _preview_text(whisper_result.text),
    )
