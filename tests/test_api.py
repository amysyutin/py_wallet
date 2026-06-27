"""Интеграционные тесты API — роутер + FastAPI + сериализация через TestClient."""

from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch

client = TestClient(app)


# ─── Smoke-тесты ────────────────────────────────────────────────────────────


def test_root():
    response = client.get("/")
    assert response.json() == {"status": "ok"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_health_ready():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@patch("app.routes._assert_database_available", side_effect=Exception("db down"))
def test_health_ready_db_unavailable(_mock_db):
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "# HELP" in response.text or "http_requests_total" in response.text


# ─── /assets ────────────────────────────────────────────────────────────────


@patch("app.routes.summarize_all")
def test_assets_endpoint_default_address(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": "0xTEST",
        "chains": [],
        "total_usd": 0.0,
    }
    response = client.get("/assets?address=0xTEST")
    assert response.status_code == 200
    data = response.json()
    assert data["address"] == "0xTEST"


def test_assets_no_address_returns_400():
    with patch("app.routes.ADDRESS_EVM", ""):
        response = client.get("/assets")
        assert response.status_code == 400


@patch("app.routes.summarize_all")
def test_assets_returns_chains_and_total(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": "0xABC",
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
    response = client.get("/assets?address=0xABC")
    assert response.status_code == 200
    data = response.json()
    assert len(data["chains"]) == 1
    assert data["chains"][0]["chain"] == "mainnet"
    assert data["total_usd"] == 3750.0


@patch("app.routes.summarize_all")
def test_assets_uses_env_address_when_param_empty(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": "0xENV",
        "chains": [],
        "total_usd": 0.0,
    }
    with patch("app.routes.ADDRESS_EVM", "0xENV"):
        response = client.get("/assets")
    assert response.status_code == 200
    assert response.json()["address"] == "0xENV"
    mock_summarize.assert_called_once_with("0xENV")


@patch("app.routes.summarize_all")
def test_assets_param_overrides_env(mock_summarize):
    mock_summarize.return_value.model_dump.return_value = {
        "address": "0xPARAM",
        "chains": [],
        "total_usd": 0.0,
    }
    with patch("app.routes.ADDRESS_EVM", "0xENV"):
        response = client.get("/assets?address=0xPARAM")
    assert response.status_code == 200
    mock_summarize.assert_called_once_with("0xPARAM")


# ─── Несуществующий эндпоинт ────────────────────────────────────────────────


def test_unknown_endpoint_returns_404():
    response = client.get("/nonexistent")
    assert response.status_code == 404
