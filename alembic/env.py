from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure the application package is on the Python path when running Alembic commands.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import models  # noqa: F401  Imported for side effects so Alembic sees models.
from app.core.config import get_settings
from app.db.base import Base

config = context.config
settings = get_settings()

# Make sure Alembic knows where migrations live and which database URL to use.
config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))


if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def _sync_database_url() -> str:
    """Return a synchronous SQLAlchemy URL for offline migrations."""

    url = make_url(settings.DATABASE_URL)
    if "+" in url.drivername:
        drivername = url.drivername.split("+", 1)[0]
        url = url.set(drivername=drivername)
    return url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""

    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations using an asynchronous SQLAlchemy engine."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
