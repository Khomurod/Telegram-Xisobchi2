"""
Speech-to-Text service — OpenAI Whisper (primary) + Google Cloud (fallback).

Whisper handles the heavy lifting with excellent multilingual recognition.
Google Cloud Speech is kept as a fallback if Whisper is unavailable.

Handles:
  - Async transcription via OpenAI Whisper API
  - Fallback to Google Cloud STT if Whisper fails / not configured
  - Structured result with confidence scoring
  - Graceful error handling with clear logging
"""
import os
import asyncio
import subprocess
import time
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


# ── OpenAI Whisper (Primary) ─────────────────────────────────

_openai_client = None


def _get_openai_client():
    """Lazy-load OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
        logger.info("OpenAI Whisper client initialized")
    return _openai_client


def _transcribe_whisper_sync(file_path: str) -> TranscriptionResult:
    """Synchronous Whisper API call — runs in thread executor."""
    start_time = time.time()

    client = _get_openai_client()
    if not client:
        raise RuntimeError("OpenAI API key not configured")

    with open(file_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="uz",
            response_format="verbose_json",
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
    # Whisper verbose_json includes segments with confidence info
    # Overall confidence is generally very high for Whisper
    confidence = 0.95 if text else 0.0
    detected_lang = getattr(response, "language", "uz")

    logger.info(f"Whisper ({elapsed:.1f}s): {text[:150]}")
    logger.info(f"Language: {detected_lang}")

    return TranscriptionResult(
        text=text,
        confidence=confidence,
        duration_seconds=elapsed,
        language=detected_lang,
    )



# ── Google Cloud STT (Fallback) ──────────────────────────────

_google_client = None


def _get_google_client():
    """Lazy-load Google Cloud Speech client."""
    global _google_client
    if _google_client is not None:
        return _google_client

    from google.cloud import speech

    # Mode 1: credentials JSON in env var (for Render, Railway, etc.)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        import tempfile, json, atexit
        json.loads(creds_json)  # Validate JSON
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            _tmp_creds_path = f.name
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name
        atexit.register(lambda p=_tmp_creds_path: os.path.exists(p) and os.remove(p))
        logger.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
    else:
        # Mode 2: file path (local dev)
        creds_path = settings.GOOGLE_CREDENTIALS_PATH
        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                f"Google credentials not found at '{creds_path}'. "
                f"Set GOOGLE_CREDENTIALS_JSON for cloud deployment."
            )
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(creds_path)
        logger.info(f"Google credentials loaded from file: {creds_path}")

    _google_client = speech.SpeechClient()
    logger.info("Google Cloud Speech client initialized")
    return _google_client


def _get_ffmpeg_path() -> str:
    """Get ffmpeg path — prefers static_ffmpeg bundle, falls back to system."""
    try:
        import static_ffmpeg
        ffmpeg_path, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg_path
    except ImportError:
        return "ffmpeg"


def _convert_ogg_to_wav(ogg_path: str) -> str:
    """Convert OGG/OPUS to LINEAR16 WAV (16kHz, mono) using ffmpeg."""
    wav_path = ogg_path.replace(".ogg", ".wav")
    ffmpeg = _get_ffmpeg_path()
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y",
                "-i", ogg_path,
                "-ar", "16000",
                "-ac", "1",
                "-sample_fmt", "s16",
                "-f", "wav",
                wav_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:200]}")
        logger.info(f"Converted to WAV: {wav_path}")
        return wav_path
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install: pip install static-ffmpeg")


def _transcribe_google_sync(file_path: str) -> TranscriptionResult:
    """Synchronous Google STT call — fallback when Whisper is unavailable."""
    from google.cloud import speech

    start_time = time.time()
    wav_path = _convert_ogg_to_wav(file_path)

    try:
        with open(wav_path, "rb") as f:
            audio_content = f.read()

        client = _get_google_client()
        audio = speech.RecognitionAudio(content=audio_content)

        speech_contexts = [speech.SpeechContext(
            phrases=[
                "ming", "yuz", "million", "milliard", "mln",
                "bir", "ikki", "uch", "to'rt", "besh",
                "olti", "yetti", "sakkiz", "to'qqiz", "o'n",
                "yigirma", "o'ttiz", "qirq", "ellik",
                "oltmish", "yetmish", "sakson", "to'qson",
                "so'm", "so'mga", "sum", "sumga", "dollar",
                "sarfladim", "ishlatdim", "oldim", "yedim", "berdim",
                "topdim", "maosh", "daromad", "kirim", "chiqim",
                "ovqat", "ovqatga", "bozor", "transport",
                "taksi", "benzin", "uy", "ijara", "kiyim",
            ],
            boost=15.0,
        )]

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=settings.SPEECH_LANGUAGE,
            alternative_language_codes=settings.SPEECH_ALT_LANGUAGES,
            enable_automatic_punctuation=True,
            model="default",
            use_enhanced=True,
            speech_contexts=speech_contexts,
        )

        response = client.recognize(config=config, audio=audio)
        elapsed = time.time() - start_time

        if not response.results:
            logger.warning("Google STT returned no results")
            return TranscriptionResult(
                text="", confidence=0.0,
                duration_seconds=elapsed,
                language=settings.SPEECH_LANGUAGE,
            )

        best = response.results[0].alternatives[0]
        detected_lang = getattr(response.results[0], "language_code", settings.SPEECH_LANGUAGE)

        logger.info(f"Google STT ({elapsed:.1f}s): {best.transcript[:150]}")
        logger.info(f"Confidence: {best.confidence:.2f} | Language: {detected_lang}")

        return TranscriptionResult(
            text=best.transcript,
            confidence=best.confidence,
            duration_seconds=elapsed,
            language=detected_lang,
        )
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass


# ── Public async API ─────────────────────────────────────────

async def transcribe_audio(file_path: str) -> TranscriptionResult:
    """
    Transcribe audio file using Whisper (primary) or Google STT (fallback).
    Non-blocking: runs API calls in thread executor.
    Cleans up all temporary files after processing.
    """
    logger.info(f"Transcribing audio: {file_path}")
    loop = asyncio.get_running_loop()

    try:
        # Primary: OpenAI Whisper (better multilingual quality)
        if os.getenv("OPENAI_API_KEY"):
            try:
                result = await loop.run_in_executor(None, _transcribe_whisper_sync, file_path)
                if result.text:
                    return result
                logger.warning("Whisper returned empty text, falling back to Google")
            except Exception as e:
                logger.warning(f"Whisper failed, falling back to Google: {e}")

        # Fallback: Google Cloud STT
        result = await loop.run_in_executor(None, _transcribe_google_sync, file_path)
        return result

    except FileNotFoundError:
        logger.error("No STT credentials configured (neither OpenAI nor Google)")
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise
    finally:
        # Clean up original OGG file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except OSError:
                pass
