import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Keep SQL echo logging opt-in so ingestion runs don't overwhelm the console.
engine = create_async_engine(
    settings.DATABASE_URL, pool_pre_ping=True, echo=settings.SQLALCHEMY_ECHO
)

if not settings.SQLALCHEMY_ECHO:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session: 
        yield session 
