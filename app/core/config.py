from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://wallet:wallet@localhost:5432/wallet"

    jwt_secret: str = "dev-insecure-change-me"
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()