"""Tests for manual wallet creation."""

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> dict[str, str]:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "password12"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "password12"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_create_manual_wallet_without_address(
    client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Manual BTC",
            "wallet_type": "manual",
            "chain_type": "manual",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["wallet_type"] == "manual"
    assert data["chain_type"] == "manual"
    assert data["address"] is None


async def test_create_manual_wallet_wrong_chain_type(
    client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Manual",
            "wallet_type": "manual",
            "chain_type": "mainnet",
        },
    )
    assert r.status_code == 422


async def test_create_evm_wallet_without_address(
    client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "EVM",
            "wallet_type": "evm",
            "chain_type": "mainnet",
        },
    )
    assert r.status_code == 422


async def test_create_evm_wallet_with_manual_chain_type(
    client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "EVM",
            "wallet_type": "evm",
            "address": "0x0000000000000000000000000000000000000001",
            "chain_type": "manual",
        },
    )
    assert r.status_code == 422


async def test_manual_wallet_assigned_to_own_group(
    client: AsyncClient, auth_headers: dict
):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Long-term"},
        )
    ).json()
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Manual BTC",
            "wallet_type": "manual",
            "chain_type": "manual",
            "group_id": group["id"],
        },
    )
    assert r.status_code == 201
    assert r.json()["group_id"] == group["id"]


async def test_manual_wallet_cannot_use_foreign_group(client: AsyncClient):
    h1 = await _register_and_login(client, "manual-owner@example.com")
    h2 = await _register_and_login(client, "manual-other@example.com")
    group = (
        await client.post("/wallet-groups", headers=h1, json={"name": "Private"})
    ).json()
    r = await client.post(
        "/wallets",
        headers=h2,
        json={
            "label": "Manual",
            "wallet_type": "manual",
            "chain_type": "manual",
            "group_id": group["id"],
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Wallet group not found"
