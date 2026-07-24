import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.wallet import Wallet

ADDRESS_A = "0x00000000000000000000000000000000000000aA"
ADDRESS_B = "0x00000000000000000000000000000000000000bB"


async def _create_evm_wallet(
    client: AsyncClient,
    auth_headers: dict,
    *,
    label: str,
    address: str,
):
    return await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": label,
            "address": address,
            "chain_type": "mainnet",
        },
    )


async def test_create_rejects_case_insensitive_active_evm_duplicate(
    client: AsyncClient,
    auth_headers: dict,
):
    first = await _create_evm_wallet(
        client,
        auth_headers,
        label="First",
        address=ADDRESS_A,
    )
    assert first.status_code == 201

    duplicate = await _create_evm_wallet(
        client,
        auth_headers,
        label="Duplicate",
        address=f"  {ADDRESS_A.swapcase()}  ",
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


async def test_manual_wallets_are_not_deduplicated(
    client: AsyncClient,
    auth_headers: dict,
):
    payload = {
        "label": "Manual",
        "wallet_type": "manual",
        "address": None,
        "chain_type": "manual",
    }
    first = await client.post("/wallets", headers=auth_headers, json=payload)
    second = await client.post("/wallets", headers=auth_headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_update_rejects_active_evm_duplicate_address(
    client: AsyncClient,
    auth_headers: dict,
):
    first = await _create_evm_wallet(
        client,
        auth_headers,
        label="First",
        address=ADDRESS_A,
    )
    second = await _create_evm_wallet(
        client,
        auth_headers,
        label="Second",
        address=ADDRESS_B,
    )
    assert first.status_code == second.status_code == 201

    updated = await client.patch(
        f"/wallets/{second.json()['id']}",
        headers=auth_headers,
        json={"address": ADDRESS_A.lower()},
    )
    assert updated.status_code == 409

    unchanged = await client.get(
        f"/wallets/{second.json()['id']}", headers=auth_headers
    )
    assert unchanged.json()["address"] == ADDRESS_B


async def test_restore_and_patch_activation_reject_active_evm_duplicate(
    client: AsyncClient,
    auth_headers: dict,
):
    old = await _create_evm_wallet(
        client,
        auth_headers,
        label="Old",
        address=ADDRESS_A,
    )
    old_id = old.json()["id"]
    assert (
        await client.delete(f"/wallets/{old_id}", headers=auth_headers)
    ).status_code == 200

    current = await _create_evm_wallet(
        client,
        auth_headers,
        label="Current",
        address=ADDRESS_A.lower(),
    )
    assert current.status_code == 201

    restored = await client.post(
        f"/wallets/{old_id}/restore",
        headers=auth_headers,
    )
    assert restored.status_code == 409

    activated = await client.patch(
        f"/wallets/{old_id}",
        headers=auth_headers,
        json={"is_active": True},
    )
    assert activated.status_code == 409


async def test_database_rejects_active_evm_duplicate(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    created = await _create_evm_wallet(
        client,
        auth_headers,
        label="Canonical",
        address=ADDRESS_A,
    )
    assert created.status_code == 201
    canonical = await db_session.get(Wallet, created.json()["id"])
    assert canonical is not None

    duplicate = Wallet(
        user_id=canonical.user_id,
        label="Concurrent duplicate",
        address=ADDRESS_A.swapcase(),
        chain_type="base",
        wallet_type="evm",
        is_active=True,
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(duplicate)
            await db_session.flush()
