from fastapi.testclient import TestClient
from app.main import app

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