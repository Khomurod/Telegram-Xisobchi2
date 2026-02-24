"""
Alembic migration environment for Xisobchi Bot.

Configured for async SQLAlchemy (aiosqlite / asyncpg).
Reads DATABASE_URL from environment — supports both SQLite (dev) and PostgreSQL (production).
"""
import os
import sys
import asyncio
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Path setup ───────────────────────────────────────────────
# Ensure project root is on sys.path so 'app' imports work.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Load .env for local runs ──────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── Import app models so Alembic can detect schema changes ────
from app.database.models import Base  # noqa: E402 — must be after sys.path setup

# Alembic Config object — gives access to values from alembic.ini
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The MetaData object to use for autogenerate support
target_metadata = Base.metadata

# ── Database URL: always read from environment ────────────────
# Falls back to the alembic.ini value if DATABASE_URL is not set.
database_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))

# Railway/Heroku give postgres:// or postgresql:// — async SQLAlchemy needs +asyncpg
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# asyncpg doesn't accept sslmode — strip it from URL
if database_url and "postgresql" in database_url:
    parsed = urlparse(database_url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    clean_query = urlencode(params, doseq=True)
    database_url = urlunparse(parsed._replace(query=clean_query))

# Alembic's async engine does not support aiosqlite/asyncpg drivers directly
# via the config file — we set it programmatically here.
config.set_main_option("sqlalchemy.url", database_url)


# ── Offline mode (generates SQL without connecting) ──────────

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This generates SQL statements without creating a DB connection.
    Useful for reviewing what will change before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online async mode (connects and applies migrations) ───────

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations in online mode."""
    # PostgreSQL (Neon pooler) needs ssl and no prepared statements
    connect_args = {}
    db = config.get_main_option("sqlalchemy.url") or ""
    if "postgresql" in db:
        connect_args = {"ssl": "require", "statement_cache_size": 0}

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration (used by 'alembic upgrade head')."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
