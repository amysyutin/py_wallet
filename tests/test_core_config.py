import secrets

import pytest
from pydantic import ValidationError

from app.core.config import (
    CI_TEST_JWT_SECRET,
    DEV_JWT_SECRET,
    Settings,
)

_FIELD_MAP = {
    "APP_ENV": "app_env",
    "JWT_SECRET": "jwt_secret",
    "JWT_ALG": "jwt_alg",
}


def _settings(**env: str | None) -> Settings:
    mapped = {_FIELD_MAP.get(key, key): value for key, value in env.items()}
    return Settings(_env_file=None, **mapped)


def test_development_no_jwt_secret_uses_dev_default():
    s = _settings(APP_ENV="development", JWT_SECRET=None)
    assert s.jwt_secret == DEV_JWT_SECRET
    assert s.using_dev_jwt_secret is True
    assert s.jwt_secret_source == "default_dev"


def test_development_explicit_dev_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="development", JWT_SECRET="dev-insecure-change-me")


def test_development_explicit_valid_secret_ok():
    secret = "a" * 32
    s = _settings(APP_ENV="development", JWT_SECRET=secret)
    assert s.jwt_secret == secret
    assert s.jwt_secret_source == "environment"
    assert s.using_dev_jwt_secret is False


def test_development_explicit_denylist_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="development", JWT_SECRET="changeme")


def test_production_missing_jwt_secret():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET=None)


def test_production_dev_insecure_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET="dev-insecure-change-me")


def test_production_ci_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET="ci-test-secret")


def test_production_short_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET="short")


def test_production_valid_generated_secret_ok():
    secret = secrets.token_urlsafe(48)
    s = _settings(APP_ENV="production", JWT_SECRET=secret)
    assert s.jwt_secret == secret
    assert len(s.jwt_secret) >= 32


def test_production_rejects_wildcard_trusted_host():
    secret = secrets.token_urlsafe(48)
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET=secret, trusted_hosts="*")


def test_trusted_hosts_are_parsed_from_csv():
    s = _settings(
        APP_ENV="test",
        JWT_SECRET=None,
        trusted_hosts="localhost, testserver,*.example.com",
    )
    assert s.trusted_host_list == ["localhost", "testserver", "*.example.com"]


def test_staging_same_rules_as_production():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="staging", JWT_SECRET=None)


def test_test_env_no_secret_uses_ci_default():
    s = _settings(APP_ENV="test", JWT_SECRET=None)
    assert s.jwt_secret == CI_TEST_JWT_SECRET
    assert s.jwt_secret_source == "default_test"


def test_test_env_explicit_ci_secret_ok():
    s = _settings(APP_ENV="test", JWT_SECRET="ci-test-secret")
    assert s.jwt_secret == "ci-test-secret"


def test_test_env_explicit_custom_secret_ok():
    s = _settings(APP_ENV="test", JWT_SECRET="another-test-secret-8")
    assert s.jwt_secret == "another-test-secret-8"


def test_test_env_disables_automatic_snapshots_by_default():
    s = _settings(APP_ENV="test", JWT_SECRET=None)
    assert s.snapshot_auto_on_wallet_create is False
    assert s.snapshot_scheduler_enabled is False


def test_test_env_allows_automatic_snapshots_to_be_enabled_explicitly():
    s = _settings(
        APP_ENV="test",
        JWT_SECRET=None,
        snapshot_auto_on_wallet_create=True,
        snapshot_scheduler_enabled=True,
    )
    assert s.snapshot_auto_on_wallet_create is True
    assert s.snapshot_scheduler_enabled is True


def test_test_env_explicit_empty_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="test", JWT_SECRET="")


def test_test_env_explicit_too_short_rejected():
    with pytest.raises(ValidationError):
        _settings(APP_ENV="test", JWT_SECRET="short")


def test_app_env_ci_alias_maps_to_test():
    s = _settings(APP_ENV="ci", JWT_SECRET=None)
    assert s.app_env == "test"
    assert s.jwt_secret == CI_TEST_JWT_SECRET


def test_jwt_secret_strips_whitespace():
    secret = "  " + "x" * 32 + "  "
    s = _settings(APP_ENV="production", JWT_SECRET=secret)
    assert s.jwt_secret == "x" * 32


def test_jwt_alg_none_rejected():
    secret = secrets.token_urlsafe(48)
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET=secret, JWT_ALG="none")


def test_jwt_alg_unknown_rejected():
    secret = secrets.token_urlsafe(48)
    with pytest.raises(ValidationError):
        _settings(APP_ENV="production", JWT_SECRET=secret, JWT_ALG="RS256")


def test_jwt_alg_hs256_ok():
    secret = secrets.token_urlsafe(48)
    s = _settings(APP_ENV="production", JWT_SECRET=secret, JWT_ALG="HS256")
    assert s.jwt_alg == "HS256"


def test_validation_error_omits_secret_value():
    secret = "my-short-secret-value"
    with pytest.raises(ValidationError) as exc_info:
        _settings(APP_ENV="production", JWT_SECRET=secret)
    assert secret not in str(exc_info.value)
