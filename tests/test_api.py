from fastapi.testclient import TestClient
from urllib3 import response
from app.main import app
from unittest.mock import patch

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.json() == {"status": "ok"}

def test_assets():
    response = client.get("/assets")
    assert response.status_code == 200

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

@patch("app.routes.summarize_binance_usdt")
def test_assets_endpoint(mock_service):

    mock_data = {
        "assets": [{"asset": "BTC", "amount": 0.1, "usd": 5000}],
        "total_usdt": 5000.0
    }
    mock_service.return_value = mock_data

    response = client.get("/binance/balance")

    assert response.status_code == 200
    data = response.json()
    assert data["total_usdt"] == 5000.0
    assert len(data["assets"]) == 1
    assert data["assets"][0]["asset"] =="BTC"

