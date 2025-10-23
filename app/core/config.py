from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "My FastAPI"
    ENV: str = "dev"
    DEBUG: bool = True

    DATABASE_URL: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
        description="Database connection string in SQLAlchemy async format.",
    )
    INIT_DB_ON_STARTUP: bool = Field(
        True,
        description=(
            "When true the application will attempt to create database tables during"
            " startup. Set to false if the database is managed externally or is not"
            " available in the current environment."
        ),
    )
    JWT_SECRET: str = "change_me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MIN: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
