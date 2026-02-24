import os
import subprocess
import sys
import sqlite3
from urllib.parse import urlparse, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("database")


def _strip_query_params(url: str) -> str:
    """Remove ALL query params from DB URL — asyncpg doesn't accept libpq params
    like sslmode, channel_binding, etc. SSL is handled via connect_args instead."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=""))


# Ensure data directory exists for SQLite
db_url = settings.DATABASE_URL
if "sqlite" in db_url:
    db_path = db_url.split("///")[-1]
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

# PostgreSQL (Neon/Supabase pooler) needs:
#   ssl='require'            — pooler enforces TLS
#   statement_cache_size=0   — PgBouncer doesn't support prepared statements
#   sslmode stripped         — asyncpg doesn't accept sslmode URL param
if "postgresql" in db_url or "postgres" in db_url:
    db_url = _strip_query_params(db_url)
    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={
            "ssl": "require",
            "statement_cache_size": 0,
        },
    )
else:
    engine = create_async_engine(db_url, echo=False)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_alembic(args: list[str]) -> subprocess.CompletedProcess:
    """Run an alembic command in a subprocess and return the result."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", alembic_ini] + args,
        cwd=project_root,
        capture_output=True,
        text=True,
    )


def _log_alembic_output(result: subprocess.CompletedProcess) -> None:
    for line in result.stdout.strip().splitlines():
        if line.strip():
            logger.info(f"[alembic] {line}")
    for line in result.stderr.strip().splitlines():
        if line.strip():
            logger.info(f"[alembic] {line}")


def _sqlite_tables_exist() -> bool:
    """
    Check if the users table exists in the SQLite database.
    Used to distinguish between:
      - A fresh empty DB  → tables don't exist → run upgrade head to CREATE
      - A pre-Alembic DB  → tables exist       → stamp then done
    Only called for SQLite; PostgreSQL uses a different path.
    """
    db_path = db_url.split("///")[-1]
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception:
        return False


async def init_db() -> None:
    """
    Apply all pending Alembic migrations on startup.

    Three scenarios handled:
    1. Fresh DB (no file, or file with no tables)
       → Run 'alembic upgrade head' to CREATE tables from the initial migration.
    2. Existing DB with tables but no alembic_version (pre-Alembic deploy)
       → Stamp as head to register existing schema WITHOUT running DDL.
         This preserves all existing user data.
    3. DB already managed by Alembic
       → Run 'alembic upgrade head' — applies only NEW migrations, no-op if current.

    Never drops, truncates, or modifies existing data.
    """
    logger.info("Checking database migrations...")

    is_postgres = "postgresql" in db_url or "postgres" in db_url

    if not is_postgres:
        # For SQLite: physically check if tables already exist
        tables_exist = _sqlite_tables_exist()

        if tables_exist:
            # Check if Alembic has already registered this DB
            check = _run_alembic(["current"])
            current_output = (check.stdout + check.stderr)
            already_managed = "(head)" in current_output or "ab1e558f6c71" in current_output

            if not already_managed:
                # Pre-Alembic DB with data: stamp without touching tables
                logger.info(
                    "Existing database detected (tables present, no Alembic version). "
                    "Stamping as current head to preserve all data..."
                )
                stamp = _run_alembic(["stamp", "head"])
                _log_alembic_output(stamp)
                if stamp.returncode != 0:
                    logger.error("Alembic stamp failed — check logs.")
                    raise RuntimeError("Database stamp failed.")
                logger.info("Database stamped. Future schema changes will migrate safely.")
                return
            # else: fall through to upgrade head (may apply new migrations)
        else:
            logger.info("Fresh database detected — running initial migration to create tables...")

    # Normal path for all cases:
    # - Fresh DB: creates tables via initial migration
    # - Already-stamped DB: no-op (or applies new migrations)
    # - PostgreSQL: always runs upgrade head
    result = _run_alembic(["upgrade", "head"])
    _log_alembic_output(result)

    if result.returncode != 0:
        logger.error(f"Alembic migration failed (exit {result.returncode})")
        raise RuntimeError("Database migration failed — check logs for details.")

    logger.info("Database is up to date.")
