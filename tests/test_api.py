from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.json() == {"status": "ok"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200


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


@patch("app.routes.summarize_binance_usdt")
def test_binance_balance(mock_service):
    mock_data = {
        "assets": [{"asset": "BTC", "amount": 0.1, "usd": 5000}],
        "total_usdt": 5000.0,
    }
    mock_service.return_value = mock_data

    response = client.get("/binance/balance")

    assert response.status_code == 200
    data = response.json()
    assert data["total_usdt"] == 5000.0
    assert len(data["assets"]) == 1
    assert data["assets"][0]["asset"] == "BTC"

