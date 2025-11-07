from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
                                
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = PROJECT_ROOT / "alembic"


def _upgrade_database(database_url: str) -> None:
    """Run Alembic migrations to ensure the schema is up to date."""

    alembic_cfg = Config(str(ALEMBIC_INI_PATH))
    alembic_cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_cfg, "head")


async def init_db() -> None:
    """Initialise the database by applying all available migrations."""

    settings = get_settings()
    await asyncio.to_thread(_upgrade_database, settings.DATABASE_URL)
