import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_login_token_works_on_protected_route(client: AsyncClient):
    email = "jwt-integ@example.com"
    password = "testpass123"
    await client.post("/auth/register", json={"email": email, "password": password})
    login = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_token_from_old_secret_rejected_after_rotation(
    client: AsyncClient, monkeypatch
):
    old_secret = "old-rotation-secret-for-tests"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", old_secret)
    get_settings.cache_clear()

    token = create_access_token(999)

    monkeypatch.setenv("JWT_SECRET", "new-rotation-secret-for-tests")
    get_settings.cache_clear()

    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
