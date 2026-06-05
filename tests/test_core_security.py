from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token


@pytest.fixture
def fresh_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-security-12")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_token_roundtrip(fresh_settings):
    token = create_access_token(42)
    assert decode_access_token(token) == "42"


def test_decode_wrong_secret(fresh_settings, monkeypatch):
    token = create_access_token(1)
    monkeypatch.setenv("JWT_SECRET", "different-secret-for-tests-99")
    get_settings.cache_clear()
    assert decode_access_token(token) is None


def test_decode_expired_token(fresh_settings):
    settings = get_settings()
    expire = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload = {"sub": "99", "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)
    assert decode_access_token(token) is None


def test_decode_malformed_token(fresh_settings):
    assert decode_access_token("not-a-valid-jwt") is None


def test_tampered_payload_fails(fresh_settings):
    token = create_access_token(7)
    parts = token.split(".")
    assert len(parts) == 3
    tampered = f"{parts[0]}.eyJzdWIiOiI5OTkifQ.{parts[2]}"
    assert decode_access_token(tampered) is None
