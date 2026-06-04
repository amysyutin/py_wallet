from unittest.mock import patch
from decimal import Decimal
from httpx import AsyncClient


async def test_register_and_me(client: AsyncClient):
    r = await client.post(
        "/auth/register",
        json={"email": "u1@example.com", "password": "password12"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "u1@example.com"

    login = await client.post(
        "/auth/login",
        json={"email": "u1@example.com", "password": "password12"},
    )
    token = login.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "u1@example.com"


async def test_register_duplicate_409(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "password12"}
    assert (await client.post("/auth/register", json=payload)).status_code == 201
    assert (await client.post("/auth/register", json=payload)).status_code == 409


async def test_wallets_create_and_list(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Test",
            "address": "0x0000000000000000000000000000000000000001",
            "chain_type": "mainnet",
        },
    )
    assert r.status_code == 201
    wallet_id = r.json()["id"]

    lst = await client.get("/wallets", headers=auth_headers)
    assert lst.status_code == 200
    assert wallet_id in [w["id"] for w in lst.json()]


@patch("app.services.snapshot.collect_wallet_balances", return_value=[])
async def test_snapshot_empty_balances(
    _mock_collect, client: AsyncClient, auth_headers: dict
):
    await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Snap",
            "address": "0x0000000000000000000000000000000000000002",
            "chain_type": "mainnet",
        },
    )
    r = await client.post("/snapshot", headers=auth_headers, json={})
    assert r.status_code == 201
    data = r.json()
    assert len(data) >= 1
    assert Decimal(data[0]["total_usd"]) == 0
    assert data[0]["balances"] == []


async def test_portfolio_history_and_summary(client: AsyncClient, auth_headers: dict):
    w = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Hist",
                "address": "0x0000000000000000000000000000000000000003",
                "chain_type": "mainnet",
            },
        )
    ).json()

    with patch("app.services.snapshot.collect_wallet_balances", return_value=[]):
        await client.post(
            "/snapshot", headers=auth_headers, json={"wallet_id": w["id"]}
        )
        await client.post(
            "/snapshot", headers=auth_headers, json={"wallet_id": w["id"]}
        )

    hist = await client.get(
        f"/portfolio?wallet_id={w['id']}&days=30",
        headers=auth_headers,
    )
    assert hist.status_code == 200
    assert len(hist.json()["points"]) == 2

    summary = await client.get("/portfolio/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["wallets_count"] >= 1


async def test_health_ok(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


async def test_register_me_includes_role_user(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "role@example.com", "password": "password12"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "role@example.com", "password": "password12"},
    )
    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "user"


async def test_binance_balance_unauthorized(client: AsyncClient):
    r = await client.get("/binance/balance")
    assert r.status_code == 403


async def test_binance_balance_forbidden_for_user(
    client: AsyncClient, auth_headers: dict
):
    r = await client.get("/binance/balance", headers=auth_headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Admin access required"


@patch("app.routes.summarize_binance_usdt")
async def test_binance_balance_ok_for_admin(
    mock_service, client: AsyncClient, admin_headers: dict
):
    mock_service.return_value = {
        "assets": [{"asset": "BTC", "amount": 0.1, "usd": 5000}],
        "total_usdt": 5000.0,
    }
    r = await client.get("/binance/balance", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["total_usdt"] == 5000.0


@patch("app.routes.summarize_binance_usdt")
async def test_binance_balance_empty(mock_service, client: AsyncClient, admin_headers: dict):
    mock_service.return_value = {"assets": [], "total_usdt": 0.0}
    r = await client.get("/binance/balance", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["total_usdt"] == 0.0


@patch("app.routes.summarize_binance_usdt")
async def test_binance_balance_error_response(
    mock_service, client: AsyncClient, admin_headers: dict
):
    mock_service.return_value = {
        "error": "Connection failed",
        "assets": [],
        "total_usdt": 0.0,
    }
    r = await client.get("/binance/balance", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["error"] == "Connection failed"


@patch("app.routes.summarize_binance_usdt")
async def test_binance_balance_multiple_assets(
    mock_service, client: AsyncClient, admin_headers: dict
):
    mock_service.return_value = {
        "assets": [
            {"asset": "BTC", "amount": 0.1, "usd": 5000},
            {"asset": "ETH", "amount": 2.0, "usd": 6000},
            {"asset": "USDT", "amount": 100, "usd": 100},
        ],
        "total_usdt": 11100.0,
    }
    r = await client.get("/binance/balance", headers=admin_headers)
    data = r.json()
    assert len(data["assets"]) == 3
    assert data["total_usdt"] == 11100.0
