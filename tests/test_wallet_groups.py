"""Tests for /wallet-groups CRUD."""

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
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_wallet_group(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/wallet-groups",
        headers=auth_headers,
        json={
            "name": "Long-term",
            "description": "Cold holdings",
            "sort_order": 10,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Long-term"
    assert data["description"] == "Cold holdings"
    assert data["sort_order"] == 10
    assert data["wallets_count"] == 0
    assert "created_at" in data
    assert "updated_at" in data


async def test_list_wallet_groups_ordered(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/wallet-groups",
        headers=auth_headers,
        json={"name": "B", "sort_order": 20},
    )
    await client.post(
        "/wallet-groups",
        headers=auth_headers,
        json={"name": "A", "sort_order": 10},
    )
    r = await client.get("/wallet-groups", headers=auth_headers)
    assert r.status_code == 200
    names = [g["name"] for g in r.json()]
    assert names == ["A", "B"]


async def test_get_wallet_group(client: AsyncClient, auth_headers: dict):
    created = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Trading"},
        )
    ).json()
    r = await client.get(f"/wallet-groups/{created['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Trading"


async def test_update_wallet_group(client: AsyncClient, auth_headers: dict):
    created = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Old"},
        )
    ).json()
    r = await client.patch(
        f"/wallet-groups/{created['id']}",
        headers=auth_headers,
        json={"name": "New", "description": "Updated"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["description"] == "Updated"


async def test_duplicate_group_name_same_user_409(
    client: AsyncClient, auth_headers: dict
):
    await client.post(
        "/wallet-groups",
        headers=auth_headers,
        json={"name": "Dup"},
    )
    r = await client.post(
        "/wallet-groups",
        headers=auth_headers,
        json={"name": "Dup"},
    )
    assert r.status_code == 409


async def test_same_group_name_different_users_allowed(client: AsyncClient):
    h1 = await _register_and_login(client, "wg-user1@example.com")
    h2 = await _register_and_login(client, "wg-user2@example.com")
    assert (
        await client.post(
            "/wallet-groups", headers=h1, json={"name": "Shared"}
        )
    ).status_code == 201
    assert (
        await client.post(
            "/wallet-groups", headers=h2, json={"name": "Shared"}
        )
    ).status_code == 201


async def test_cannot_access_another_users_group(client: AsyncClient):
    h1 = await _register_and_login(client, "wg-owner@example.com")
    h2 = await _register_and_login(client, "wg-other@example.com")
    created = (
        await client.post(
            "/wallet-groups", headers=h1, json={"name": "Private"}
        )
    ).json()
    assert (
        await client.get(f"/wallet-groups/{created['id']}", headers=h2)
    ).status_code == 404
    assert (
        await client.patch(
            f"/wallet-groups/{created['id']}",
            headers=h2,
            json={"name": "Hacked"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/wallet-groups/{created['id']}", headers=h2)
    ).status_code == 404


async def test_delete_group_does_not_delete_wallets(
    client: AsyncClient, auth_headers: dict
):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "ToDelete"},
        )
    ).json()
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "W1",
                "address": "0x00000000000000000000000000000000000000aa",
                "chain_type": "mainnet",
                "group_id": group["id"],
            },
        )
    ).json()
    assert wallet["group_id"] == group["id"]

    r = await client.delete(f"/wallet-groups/{group['id']}", headers=auth_headers)
    assert r.status_code == 204

    assert (
        await client.get(f"/wallet-groups/{group['id']}", headers=auth_headers)
    ).status_code == 404

    wallet_after = (
        await client.get(f"/wallets/{wallet['id']}", headers=auth_headers)
    ).json()
    assert wallet_after["id"] == wallet["id"]
    assert wallet_after["group_id"] is None


async def test_new_user_has_no_default_group(client: AsyncClient):
    headers = await _register_and_login(client, "no-default@example.com")
    r = await client.get("/wallet-groups", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


async def test_wallets_count_on_group(client: AsyncClient, auth_headers: dict):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Counted"},
        )
    ).json()
    for i in range(2):
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": f"W{i}",
                "address": f"0x00000000000000000000000000000000000000{i:02x}",
                "chain_type": "mainnet",
                "group_id": group["id"],
            },
        )
    r = await client.get(f"/wallet-groups/{group['id']}", headers=auth_headers)
    assert r.json()["wallets_count"] == 2
