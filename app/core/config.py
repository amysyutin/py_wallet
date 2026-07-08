from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-insecure-change-me"
CI_TEST_JWT_SECRET = "ci-test-secret"
ALLOWED_JWT_ALGS = frozenset({"HS256"})

INSECURE_JWT_SECRETS = frozenset(
    {
        "dev-insecure-change-me",
        "ci-test-secret",
        "changeme",
        "secret",
        "jwt-secret",
        "your-secret-key",
        "test",
        "testing",
        "password",
        "12345678",
    }
)

AppEnv = Literal["development", "test", "staging", "production"]
JwtSecretSource = Literal["environment", "default_dev", "default_test"]

_MIN_JWT_SECRET_LEN = {
    "development": 16,
    "test": 8,
    "staging": 32,
    "production": 32,
}


def normalize_app_env(value: str) -> AppEnv:
    normalized = value.strip().lower()
    if normalized == "ci":
        return "test"
    if normalized in ("development", "test", "staging", "production"):
        return normalized  # type: ignore[return-value]
    raise ValueError(
        f"Invalid APP_ENV: {value}. "
        "Allowed: development, test, staging, production (ci is alias for test)"
    )


def _is_denylisted(secret: str) -> bool:
    return secret.strip().lower() in INSECURE_JWT_SECRETS


def resolve_jwt_secret(
    raw: str | None,
    app_env: AppEnv,
) -> tuple[str, JwtSecretSource, bool]:
    if raw is None:
        if app_env == "development":
            return DEV_JWT_SECRET, "default_dev", True
        if app_env == "test":
            return CI_TEST_JWT_SECRET, "default_test", False
        return "", "environment", False

    return raw.strip(), "environment", False


def validate_jwt_secret(secret: str, app_env: AppEnv, *, explicit: bool) -> None:
    if app_env in ("staging", "production"):
        if not secret:
            raise ValueError(
                "JWT_SECRET is required when APP_ENV is staging or production"
            )
        if _is_denylisted(secret):
            raise ValueError(
                "JWT_SECRET is not allowed (insecure or placeholder value)"
            )
        if len(secret) < _MIN_JWT_SECRET_LEN[app_env]:
            raise ValueError(
                "JWT_SECRET is too short for production (minimum 32 characters)"
            )
        return

    if app_env == "development":
        if not explicit:
            return
        if not secret:
            raise ValueError("JWT_SECRET cannot be empty")
        if _is_denylisted(secret):
            raise ValueError(
                "JWT_SECRET is not allowed (insecure or placeholder value)"
            )
        if len(secret) < _MIN_JWT_SECRET_LEN["development"]:
            raise ValueError(
                "JWT_SECRET is too short for development (minimum 16 characters)"
            )
        return

    if app_env == "test":
        if not secret:
            raise ValueError("JWT_SECRET cannot be empty")
        if explicit and len(secret) < _MIN_JWT_SECRET_LEN["test"]:
            raise ValueError("JWT_SECRET is too short for test (minimum 8 characters)")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://wallet:wallet@localhost:5432/wallet"

    app_env: AppEnv = "development"
    jwt_secret: str | None = None
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 60
    snapshot_service_url: str = "http://localhost:8001"
    snapshot_internal_api_token: str = ""
    snapshot_service_timeout_seconds: float = Field(default=5.0, gt=0)
    snapshot_auto_on_wallet_create: bool = True
    snapshot_scheduler_enabled: bool = True
    snapshot_scheduler_interval_seconds: int = Field(default=300, gt=0)

    jwt_secret_source: JwtSecretSource = Field(default="environment", exclude=True)
    using_dev_jwt_secret: bool = Field(default=False, exclude=True)

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env_field(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "ci":
                return "test"
        return value

    @field_validator("jwt_alg")
    @classmethod
    def validate_jwt_alg(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized == "NONE":
            raise ValueError("JWT_ALG=none is not allowed")
        if normalized not in ALLOWED_JWT_ALGS:
            raise ValueError(f"Unsupported JWT_ALG: {value}. Allowed: HS256")
        return normalized

    @model_validator(mode="after")
    def resolve_and_validate_jwt_secret(self) -> Self:
        env = normalize_app_env(self.app_env)
        self.app_env = env

        if self.jwt_secret is None:
            raw_present = False
            raw = None
        elif str(self.jwt_secret).strip() == "":
            raw_present = True
            raw = ""
        else:
            raw_present = True
            raw = str(self.jwt_secret).strip()

        resolved, source, using_dev = resolve_jwt_secret(raw, env)
        validate_jwt_secret(resolved, env, explicit=raw_present)

        self.jwt_secret = resolved
        self.jwt_secret_source = source
        self.using_dev_jwt_secret = using_dev
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
