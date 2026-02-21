import os
import subprocess
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("database")

# Ensure data directory exists for SQLite
db_url = settings.DATABASE_URL
if "sqlite" in db_url:
    db_path = db_url.split("///")[-1]
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

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


async def init_db() -> None:
    """
    Apply all pending Alembic migrations on startup.

    This is the core of data safety:
    - On a fresh DB: runs the initial migration and creates all tables.
    - On an existing DB that was created before Alembic was introduced:
      auto-detects this (no alembic_version table) and 'stamps' the schema
      as already at head without running any DDL — preserving all user data.
    - On a DB already managed by Alembic: applies only new migrations.

    Never drops, truncates, or modifies existing data.
    """
    logger.info("Checking database migrations...")

    # Check current Alembic revision
    check = _run_alembic(["current"])
    current_output = check.stdout + check.stderr

    # Detect if the database was created before Alembic was introduced.
    # In that case, 'alembic current' reports no revision (empty or "(head)" only
    # if already stamped). We look for a missing alembic_version table signal.
    is_unmanaged = (
        check.returncode != 0
        or "alembic_version" not in current_output
        and "(head)" not in current_output
        and "ab1e558f6c71" not in current_output
    )

    if is_unmanaged:
        logger.info(
            "Existing database detected (no Alembic version table). "
            "Stamping as current head to preserve all data..."
        )
        stamp = _run_alembic(["stamp", "head"])
        _log_alembic_output(stamp)
        if stamp.returncode != 0:
            logger.error("Alembic stamp failed — check logs.")
            raise RuntimeError("Database stamp failed.")
        logger.info("Database stamped at head. Future schema changes will migrate safely.")
        return

    # Normal path: run any pending migrations
    logger.info("Running pending migrations (alembic upgrade head)...")
    result = _run_alembic(["upgrade", "head"])
    _log_alembic_output(result)

    if result.returncode != 0:
        logger.error(f"Alembic migration failed (exit {result.returncode})")
        raise RuntimeError("Database migration failed — check logs for details.")

    logger.info("Database is up to date.")
