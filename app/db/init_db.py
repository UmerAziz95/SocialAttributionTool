from __future__ import annotations

from app.db.base import Base
from app.db.session import engine

# Import models so that SQLAlchemy is aware of them when creating tables.
from app import models  # noqa: F401  (imported for side effects)


async def init_db() -> None:
    """Initialise database schema by creating all tables."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
