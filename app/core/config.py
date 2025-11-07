from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    APP_NAME: str = "My FastAPI"
    ENV: str = "dev"
    DEBUG: bool = True

    DATABASE_URL: str = Field(
        ...,
        description="Database connection string in SQLAlchemy async format.",
    )
    INIT_DB_ON_STARTUP: bool = Field(
        True,
        description=(
            "When true the application will apply Alembic migrations during"
            " startup to ensure the schema is up to date. Set to false if the"
            " database is managed externally or is not available in the current"
            " environment."
        ),                                                        
    )        
    JWT_SECRET: str = Field(
        ...,
        description="Secret used to sign JWT access tokens.",
    )
    JWT_ALG: str = "HS256"                                                                
    ACCESS_TOKEN_EXPIRE_MIN: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()   
