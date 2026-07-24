"""Интеграционные тесты API — роутер + FastAPI + сериализация через TestClient."""

import asyncio

from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest

import app.routes as app_routes

client = TestClient(app)

ADDRESS_A = "0x" + "a" * 40
ADDRESS_B = "0x" + "b" * 40
ADDRESS_C = "0x" + "c" * 40


@pytest.fixture(autouse=True)
def clear_assets_cache():
    app_routes._clear_assets_cache()
    yield
    app_routes._clear_assets_cache()


# ─── Smoke-тесты ────────────────────────────────────────────────────────────


def test_root():
    response = client.get("/")
    assert response.json() == {"status": "ok"}


def test_untrusted_host_is_rejected():
    response = client.get("/", headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["version"] == "0.2.0"
    assert response.json()["build_sha"] == "unknown"


def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert response.json()["version"] == "0.2.0"
    assert response.json()["build_sha"] == "unknown"


def test_health_ready():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["version"] == "0.2.0"
    assert response.json()["build_sha"] == "unknown"


def test_health_exposes_configured_release_metadata():
    release = SimpleNamespace(app_version="2.4.1", build_sha="6350ab10")
    with patch("app.routes.get_settings", return_value=release):
        response = client.get("/health/live")

    assert response.json() == {
        "status": "alive",
        "version": "2.4.1",
        "build_sha": "6350ab10",
    }


def test_openapi_exposes_application_version():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["version"] == "0.2.0"


@patch("app.routes._assert_database_available", side_effect=Exception("db down"))
def test_health_ready_db_unavailable(_mock_db):
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"


def test_health_ready_snapshot_schema_missing():
    connection = AsyncMock()
    connection.scalar.return_value = False
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)
    unavailable_engine = MagicMock()
    unavailable_engine.connect.return_value = connection_context

    with patch("app.routes.engine", unavailable_engine):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"
    connection.execute.assert_awaited_once()
    connection.scalar.assert_awaited_once()


def test_health_ready_can_skip_snapshot_schema_for_isolated_smoke():
    connection = AsyncMock()
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)
    isolated_engine = MagicMock()
    isolated_engine.connect.return_value = connection_context
    isolated_settings = SimpleNamespace(
        app_version="0.2.0",
        build_sha="isolated-smoke",
        snapshot_schema_required=False,
    )

    with (
        patch("app.routes.engine", isolated_engine),
        patch("app.routes.get_settings", return_value=isolated_settings),
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    connection.execute.assert_awaited_once()
    connection.scalar.assert_not_awaited()


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "# HELP" in response.text or "http_requests_total" in response.text
    assert "py_wallet_build_info" in response.text
    assert "py_wallet_snapshot_job_create_total" in response.text


# ─── /assets ────────────────────────────────────────────────────────────────


@patch("app.routes.summarize_all")
def test_assets_endpoint_default_address(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_A,
        "chains": [],
        "total_usd": 0.0,
    }
    response = client.get(f"/assets?address={ADDRESS_A}")
    assert response.status_code == 200
    data = response.json()
    assert data["address"] == ADDRESS_A


def test_assets_no_address_returns_400():
    with patch("app.routes.ADDRESS_EVM", ""):
        response = client.get("/assets")
        assert response.status_code == 400


def test_assets_invalid_address_returns_422():
    response = client.get("/assets?address=0xTEST")
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid EVM address"


@patch("app.routes.summarize_all")
def test_assets_returns_chains_and_total(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_A,
        "chains": [
            {
                "chain": "mainnet",
                "native_symbol": "ETH",
                "native_amount": 1.0,
                "usdt_amount": 500.0,
                "usdc_amount": 250.0,
                "tokens": [],
            }
        ],
        "total_usd": 3750.0,
    }
    response = client.get(f"/assets?address={ADDRESS_A}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["chains"]) == 1
    assert data["chains"][0]["chain"] == "mainnet"
    assert data["total_usd"] == 3750.0


@patch("app.routes.summarize_all")
def test_assets_uses_env_address_when_param_empty(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_B,
        "chains": [],
        "total_usd": 0.0,
    }
    with patch("app.routes.ADDRESS_EVM", ADDRESS_B):
        response = client.get("/assets")
    assert response.status_code == 200
    assert response.json()["address"] == ADDRESS_B
    mock_summarize.assert_called_once_with(ADDRESS_B)


@patch("app.routes.summarize_all")
def test_assets_param_overrides_env(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_C,
        "chains": [],
        "total_usd": 0.0,
    }
    with patch("app.routes.ADDRESS_EVM", ADDRESS_B):
        response = client.get(f"/assets?address={ADDRESS_C}")
    assert response.status_code == 200
    mock_summarize.assert_called_once_with(ADDRESS_C)


@patch("app.routes.summarize_all")
def test_assets_caches_same_address(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_A,
        "chains": [],
        "total_usd": 100.0,
    }

    first = client.get(f"/assets?address={ADDRESS_A}")
    second = client.get(f"/assets?address={ADDRESS_A.upper().replace('0X', '0x')}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    mock_summarize.assert_called_once_with(ADDRESS_A)


@patch("app.routes.summarize_all")
def test_assets_cache_expires(mock_summarize, monkeypatch):
    now = 100.0
    monkeypatch.setattr(app_routes, "monotonic", lambda: now)
    mock_summarize.return_value.model_dump.return_value = {
        "address": ADDRESS_A,
        "chains": [],
        "total_usd": 100.0,
    }

    assert client.get(f"/assets?address={ADDRESS_A}").status_code == 200
    now += app_routes.ASSETS_CACHE_TTL_SECONDS + 1
    assert client.get(f"/assets?address={ADDRESS_A}").status_code == 200

    assert mock_summarize.call_count == 2


def test_assets_returns_429_when_lookup_capacity_is_busy(monkeypatch):
    class BusyLookupSlots:
        async def acquire(self):
            await asyncio.sleep(1)

        def release(self):
            raise AssertionError("unacquired slot must not be released")

    monkeypatch.setattr(app_routes, "_assets_lookup_slots", BusyLookupSlots())
    monkeypatch.setattr(app_routes, "ASSETS_QUEUE_TIMEOUT_SECONDS", 0.001)

    response = client.get(f"/assets?address={ADDRESS_A}")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"


# ─── Несуществующий эндпоинт ────────────────────────────────────────────────


def test_unknown_endpoint_returns_404():
    response = client.get("/nonexistent")
    assert response.status_code == 404
