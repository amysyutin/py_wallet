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
    app_version: str = Field(default="0.2.0", min_length=1, max_length=128)
    build_sha: str = Field(default="unknown", min_length=1, max_length=128)
    trusted_hosts: str = "localhost,127.0.0.1,test,testserver"
    jwt_secret: str | None = None
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 60
    snapshot_service_url: str = "http://localhost:8001"
    snapshot_internal_api_token: str = ""
    snapshot_service_timeout_seconds: float = Field(default=5.0, gt=0)
    snapshot_schema_required: bool = True
    snapshot_auto_on_wallet_create: bool = True
    snapshot_scheduler_enabled: bool = True
    snapshot_scheduler_interval_seconds: int = Field(default=300, gt=0)
    telegram_bot_token: str = ""
    telegram_bot_username: str = "py_WalletBot"
    telegram_mini_app_url: str = "https://pywallet.dev/telegram"
    telegram_webhook_url: str = "https://pywallet.dev/api/telegram/webhook"
    telegram_webhook_secret: str = Field(
        default="", max_length=256, pattern=r"^[A-Za-z0-9_-]*$"
    )
    telegram_auth_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    telegram_daily_balance_enabled: bool = False

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

    @field_validator("app_version", "build_sha", mode="before")
    @classmethod
    def normalize_release_metadata(cls, value: object, info) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "0.2.0" if info.field_name == "app_version" else "unknown"
        if isinstance(value, str):
            return value.strip()
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

        if env == "test":
            if "snapshot_auto_on_wallet_create" not in self.model_fields_set:
                self.snapshot_auto_on_wallet_create = False
            if "snapshot_scheduler_enabled" not in self.model_fields_set:
                self.snapshot_scheduler_enabled = False

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
        if not self.trusted_host_list:
            raise ValueError("TRUSTED_HOSTS must contain at least one host")
        if env in ("staging", "production") and "*" in self.trusted_host_list:
            raise ValueError(
                "TRUSTED_HOSTS cannot contain '*' in staging or production"
            )
        return self

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
