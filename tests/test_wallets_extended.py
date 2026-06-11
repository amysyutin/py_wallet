"""Tests for extended wallet CRUD and migration backfill behavior."""

from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.user import User
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup


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


async def test_create_wallet_with_group(client: AsyncClient, auth_headers: dict):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "MyGroup"},
        )
    ).json()
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "ETH",
            "address": "0x0000000000000000000000000000000000000001",
            "chain_type": "mainnet",
            "group_id": group["id"],
            "notes": "note",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["group_id"] == group["id"]
    assert data["wallet_type"] == "evm"
    assert data["is_active"] is True
    assert data["notes"] == "note"
    assert "updated_at" in data


async def test_create_wallet_defaults(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Basic",
            "address": "0x0000000000000000000000000000000000000002",
            "chain_type": "mainnet",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["wallet_type"] == "evm"
    assert data["is_active"] is True
    assert data["group_id"] is None


async def test_create_wallet_manual_type_rejected(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "Manual",
            "wallet_type": "manual",
            "address": "0x0000000000000000000000000000000000000003",
            "chain_type": "mainnet",
        },
    )
    assert r.status_code == 422


async def test_create_wallet_foreign_group_404(client: AsyncClient):
    h1 = await _register_and_login(client, "w-owner@example.com")
    h2 = await _register_and_login(client, "w-other@example.com")
    group = (
        await client.post(
            "/wallet-groups", headers=h1, json={"name": "Private"}
        )
    ).json()
    r = await client.post(
        "/wallets",
        headers=h2,
        json={
            "label": "Bad",
            "address": "0x0000000000000000000000000000000000000004",
            "chain_type": "mainnet",
            "group_id": group["id"],
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Wallet group not found"


async def test_get_wallet_not_found(client: AsyncClient, auth_headers: dict):
    r = await client.get("/wallets/99999", headers=auth_headers)
    assert r.status_code == 404


async def test_get_wallet_other_user_404(client: AsyncClient):
    h1 = await _register_and_login(client, "w-get-owner@example.com")
    h2 = await _register_and_login(client, "w-get-other@example.com")
    wallet = (
        await client.post(
            "/wallets",
            headers=h1,
            json={
                "label": "Mine",
                "address": "0x0000000000000000000000000000000000000005",
                "chain_type": "mainnet",
            },
        )
    ).json()
    assert (await client.get(f"/wallets/{wallet['id']}", headers=h2)).status_code == 404


async def test_patch_wallet(client: AsyncClient, auth_headers: dict):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "PatchGroup"},
        )
    ).json()
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Old",
                "address": "0x0000000000000000000000000000000000000006",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={
            "label": "New",
            "group_id": group["id"],
            "is_active": False,
            "notes": "patched",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["label"] == "New"
    assert data["group_id"] == group["id"]
    assert data["is_active"] is False
    assert data["notes"] == "patched"


async def test_patch_forbidden_fields_rejected(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Immutable",
                "address": "0x0000000000000000000000000000000000000007",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"address": "0x000000000000000000000000000000000000ffff"},
    )
    assert r.status_code == 422


async def test_soft_delete_wallet(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "DeleteMe",
                "address": "0x0000000000000000000000000000000000000008",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False


async def test_delete_wallet_idempotent(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Twice",
                "address": "0x0000000000000000000000000000000000000009",
                "chain_type": "mainnet",
            },
        )
    ).json()
    assert (await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)).status_code == 200
    r = await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False


async def test_list_wallets_active_only_default(client: AsyncClient, auth_headers: dict):
    active = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Active",
                "address": "0x000000000000000000000000000000000000000a",
                "chain_type": "mainnet",
            },
        )
    ).json()
    inactive = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Inactive",
                "address": "0x000000000000000000000000000000000000000b",
                "chain_type": "mainnet",
            },
        )
    ).json()
    await client.delete(f"/wallets/{inactive['id']}", headers=auth_headers)

    default_list = (await client.get("/wallets", headers=auth_headers)).json()
    assert [w["id"] for w in default_list] == [active["id"]]

    all_list = (
        await client.get("/wallets?active_only=false", headers=auth_headers)
    ).json()
    assert {w["id"] for w in all_list} == {active["id"], inactive["id"]}


@patch("app.services.snapshot.collect_wallet_balances", return_value=[])
async def test_snapshot_inactive_wallet_400(
    _mock, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "InactiveSnap",
                "address": "0x000000000000000000000000000000000000000c",
                "chain_type": "mainnet",
            },
        )
    ).json()
    await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    r = await client.post(
        "/snapshot",
        headers=auth_headers,
        json={"wallet_id": wallet["id"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Wallet is inactive"


@patch("app.services.snapshot.collect_wallet_balances", return_value=[])
async def test_snapshot_all_skips_inactive(
    _mock, client: AsyncClient, auth_headers: dict
):
    active = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "ActiveSnap",
                "address": "0x000000000000000000000000000000000000000d",
                "chain_type": "mainnet",
            },
        )
    ).json()
    inactive = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "InactiveSnapAll",
                "address": "0x000000000000000000000000000000000000000e",
                "chain_type": "mainnet",
            },
        )
    ).json()
    await client.delete(f"/wallets/{inactive['id']}", headers=auth_headers)

    r = await client.post("/snapshot", headers=auth_headers, json={})
    assert r.status_code == 201
    wallet_ids = {s["wallet_id"] for s in r.json()}
    assert active["id"] in wallet_ids
    assert inactive["id"] not in wallet_ids


async def test_migration_backfill_attaches_default_group(db_session: AsyncSession):
    """Simulates PR2 migration backfill: existing wallet → Default group."""
    user = User(email="backfill@example.com", auth_hash=hash_password("password12"))
    db_session.add(user)
    await db_session.flush()

    default_group = WalletGroup(user_id=user.id, name="Default", sort_order=0)
    db_session.add(default_group)
    await db_session.flush()

    wallet = Wallet(
        user_id=user.id,
        label="Legacy",
        address="0x00000000000000000000000000000000000000bb",
        chain_type="mainnet",
        wallet_type="evm",
        is_active=True,
        group_id=None,
    )
    db_session.add(wallet)
    await db_session.flush()

    await db_session.execute(
        text(
            """
            UPDATE wallets w
            SET group_id = wg.id
            FROM wallet_groups wg
            WHERE wg.user_id = w.user_id
              AND wg.name = 'Default'
              AND w.id = :wallet_id
            """
        ),
        {"wallet_id": wallet.id},
    )
    await db_session.refresh(wallet)

    group = await db_session.scalar(
        select(WalletGroup).where(WalletGroup.id == wallet.group_id)
    )
    assert wallet.group_id is not None
    assert group is not None
    assert group.name == "Default"
    assert group.user_id == wallet.user_id
