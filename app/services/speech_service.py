"""
Google Cloud Speech-to-Text service.

Handles:
  - OGG/OPUS → WAV (LINEAR16, 16kHz, mono) conversion via ffmpeg
  - Async transcription via Google Cloud STT API
  - Structured result with confidence scoring
  - Graceful error handling with clear logging
"""
import os
import asyncio
import subprocess
import time
from dataclasses import dataclass
from typing import Optional
from google.cloud import speech
from google.api_core import exceptions as gcp_exceptions
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


# ── Client singleton ─────────────────────────────────────────

_client: Optional[speech.SpeechClient] = None


def _get_client() -> speech.SpeechClient:
    """Lazy-load Google Cloud Speech client.
    Supports two credential modes:
    1. GOOGLE_CREDENTIALS_JSON env var (cloud/Railway) — full JSON as string
    2. GOOGLE_APPLICATION_CREDENTIALS file path (local) — path to JSON file
    """
    global _client
    if _client is None:
        # Mode 1: credentials JSON in env var (for Railway, render, etc.)
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            import tempfile, json, atexit
            # Validate it's proper JSON before writing
            json.loads(creds_json)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(creds_json)
                _tmp_creds_path = f.name
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name
            # Register cleanup so the private key doesn't linger on disk (Finding #3 fix)
            atexit.register(lambda p=_tmp_creds_path: os.path.exists(p) and os.remove(p))
            logger.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
        else:
            # Mode 2: file path (local dev)
            creds_path = settings.GOOGLE_CREDENTIALS_PATH
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Google credentials not found at '{creds_path}'. "
                    f"Set GOOGLE_APPLICATION_CREDENTIALS in .env, or "
                    f"set GOOGLE_CREDENTIALS_JSON for cloud deployment."
                )
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(creds_path)
            logger.info(f"Google credentials loaded from file: {creds_path}")

        _client = speech.SpeechClient()
        logger.info("Google Cloud Speech client initialized")
    return _client


# ── Audio conversion (ffmpeg subprocess) ─────────────────────

def _get_ffmpeg_path() -> str:
    """Get ffmpeg path — prefers static_ffmpeg bundle, falls back to system."""
    try:
        import static_ffmpeg
        ffmpeg_path, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg_path
    except ImportError:
        return "ffmpeg"  # Fall back to system ffmpeg


def _convert_ogg_to_wav(ogg_path: str) -> str:
    """Convert OGG/OPUS to LINEAR16 WAV (16kHz, mono) using ffmpeg."""
    wav_path = ogg_path.replace(".ogg", ".wav")
    ffmpeg = _get_ffmpeg_path()
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y",          # Overwrite output
                "-i", ogg_path,        # Input file
                "-ar", "16000",        # Sample rate 16kHz
                "-ac", "1",            # Mono channel
                "-sample_fmt", "s16",  # 16-bit signed int (LINEAR16)
                "-f", "wav",           # Output format
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
        raise RuntimeError(
            "ffmpeg not found. Install: pip install static-ffmpeg"
        )


# ── Synchronous transcription (runs in executor) ─────────────

def _transcribe_sync(file_path: str) -> TranscriptionResult:
    """Synchronous Google STT call — to be run in thread executor."""
    start_time = time.time()

    # Step 1: Convert OGG to WAV
    wav_path = _convert_ogg_to_wav(file_path)

    try:
        # Step 2: Read audio bytes
        with open(wav_path, "rb") as f:
            audio_content = f.read()

        # Step 3: Configure recognition
        client = _get_client()
        audio = speech.RecognitionAudio(content=audio_content)
        # Speech adaptation: boost Uzbek number/financial words
        speech_contexts = [speech.SpeechContext(
            phrases=[
                # Number words — critical for correct digit splitting
                "ming", "yuz", "million", "milliard", "mln",
                "bir", "ikki", "uch", "to'rt", "besh",
                "olti", "yetti", "sakkiz", "to'qqiz", "o'n",
                "yigirma", "o'ttiz", "qirq", "ellik",
                "oltmish", "yetmish", "sakson", "to'qson",
                # Currency
                "so'm", "so'mga", "sum", "sumga", "dollar",
                # Transaction words
                "sarfladim", "ishlatdim", "oldim", "yedim", "berdim",
                "topdim", "maosh", "daromad", "kirim", "chiqim",
                # Categories
                "ovqat", "ovqatga", "bozor", "bozorlik", "transport",
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

        # Step 4: Call API
        response = client.recognize(config=config, audio=audio)

        elapsed = time.time() - start_time

        if not response.results:
            logger.warning("Google STT returned no results")
            return TranscriptionResult(
                text="", confidence=0.0,
                duration_seconds=elapsed,
                language=settings.SPEECH_LANGUAGE,
            )

        # Step 5: Extract best result
        best = response.results[0].alternatives[0]
        detected_lang = getattr(response.results[0], "language_code", settings.SPEECH_LANGUAGE)

        logger.info(f"Transcription ({elapsed:.1f}s): {best.transcript[:150]}")
        logger.info(f"Confidence: {best.confidence:.2f} | Language: {detected_lang}")

        return TranscriptionResult(
            text=best.transcript,
            confidence=best.confidence,
            duration_seconds=elapsed,
            language=detected_lang,
        )

    finally:
        # Clean up WAV file
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass


# ── Public async API ─────────────────────────────────────────

async def transcribe_audio(file_path: str) -> TranscriptionResult:
    """
    Transcribe audio file using Google Cloud Speech-to-Text.
    Non-blocking: runs conversion + API call in thread executor.
    Cleans up all temporary files after processing.
    """
    logger.info(f"Transcribing audio: {file_path}")
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _transcribe_sync, file_path)
        return result

    except FileNotFoundError as e:
        logger.error(f"Credentials error: {e}")
        raise
    except gcp_exceptions.InvalidArgument as e:
        logger.error(f"Invalid audio format: {e}")
        raise
    except gcp_exceptions.ResourceExhausted as e:
        logger.error(f"API quota exceeded: {e}")
        raise
    except gcp_exceptions.Unauthenticated as e:
        logger.error(f"Invalid credentials: {e}")
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise
    finally:
        # Clean up original OGG file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except OSError:
                pass
