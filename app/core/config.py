from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # pydantic v2 settings config
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "My FastAPI"
    ENV: str = "dev"  # <-- add this since you have ENV=dev in .env
    DEBUG: bool = True

    DATABASE_URL: str = Field(..., description="postgresql+asyncpg://user:pass@host:5432/db")
    JWT_SECRET: str = "change_me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MIN: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

@lru_cache
def get_settings() -> Settings:
    return Settings()
