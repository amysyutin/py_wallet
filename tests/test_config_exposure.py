import json
import logging

import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET, Settings
from app.log import SecretFilter
from app.main import app


def test_validation_error_does_not_contain_secret():
    secret = "my-short-secret-value"
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret=secret,
        )
    assert secret not in str(exc_info.value)


def test_openapi_schema_has_no_jwt_secret():
    schema = json.dumps(app.openapi())
    assert "jwt_secret" not in schema
    assert "JWT_SECRET" not in schema


def test_settings_not_in_route_response_models():
    for route in app.routes:
        response_model = getattr(route, "response_model", None)
        if response_model is None:
            continue
        name = getattr(response_model, "__name__", str(response_model))
        assert name != "Settings"


def test_startup_log_format_does_not_contain_secrets(caplog):
    caplog.set_level(logging.INFO)
    with caplog.at_level(logging.WARNING):
        from app.main import lifespan

        async def _run():
            async with lifespan(app):
                pass

        import asyncio

        asyncio.run(_run())

    combined = caplog.text
    assert DEV_JWT_SECRET not in combined
    assert "ci-test-secret" not in combined


def test_secret_filter_redacts_key_value_pairs():
    filt = SecretFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="config JWT_SECRET=super-secret-value-here",
        args=(),
        exc_info=None,
    )
    filt.filter(record)
    assert "super-secret-value-here" not in str(record.msg)
    assert "***" in str(record.msg)
