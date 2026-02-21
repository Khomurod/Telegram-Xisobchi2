import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    MODE: str = os.getenv("MODE", "polling")  # "polling" or "webhook"

    # Database
    # Railway provides DATABASE_URL as postgresql://...
    # SQLAlchemy async needs postgresql+asyncpg://...
    # This auto-conversion makes it work without manual env var editing.
    @property
    def DATABASE_URL(self) -> str:
        raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/xisobchi.db")
        # Railway/Heroku use postgres:// or postgresql:// — convert to async driver
        if raw.startswith("postgres://"):
            return raw.replace("postgres://", "postgresql+asyncpg://", 1)
        if raw.startswith("postgresql://"):
            return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        return raw


    # Google Cloud Speech-to-Text
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    SPEECH_LANGUAGE: str = os.getenv("SPEECH_LANGUAGE", "uz-UZ")
    SPEECH_ALT_LANGUAGES: list = os.getenv("SPEECH_ALT_LANGUAGES", "ru-RU").split(",")

    # Voice limits
    MAX_VOICE_DURATION: int = int(os.getenv("MAX_VOICE_DURATION", "60"))
    VOICE_RATE_LIMIT: int = int(os.getenv("VOICE_RATE_LIMIT", "10"))  # per minute per user

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def webhook_full_url(self) -> str:
        return f"{self.WEBHOOK_URL}{self.WEBHOOK_PATH}"

    @property
    def is_webhook(self) -> bool:
        return self.MODE == "webhook"


settings = Settings()
