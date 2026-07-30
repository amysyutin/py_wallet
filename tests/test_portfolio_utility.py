from datetime import datetime, timedelta, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot_service import (
    ChainSnapshot,
    SnapshotBalanceSnapshot,
    SnapshotRun,
    WalletSnapshot,
)
from app.db.models.wallet import Wallet


async def _create_wallet(
    client: AsyncClient,
    headers: dict,
    *,
    suffix: int,
    group_id: int | None = None,
) -> int:
    response = await client.post(
        "/wallets",
        headers=headers,
        json={
            "label": f"Utility {suffix}",
            "address": f"0x{suffix:040x}",
            "chain_type": "mainnet",
            "group_id": group_id,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _add_snapshot(
    session: AsyncSession,
    wallet: Wallet,
    *,
    observed_at: datetime,
    total_usd: Decimal,
    wallet_status: str = "success",
    chain_status: str = "success",
    assets: list[tuple[str, str, Decimal]] | None = None,
) -> None:
    run = SnapshotRun(
        user_id=wallet.user_id,
        wallet_id=wallet.id,
        group_id=wallet.group_id,
        trigger_type="manual",
        scope_type="wallet",
        status=wallet_status,
        created_at=observed_at - timedelta(seconds=10),
        finished_at=observed_at,
    )
    session.add(run)
    await session.flush()
    wallet_snapshot = WalletSnapshot(
        snapshot_run_id=run.id,
        wallet_id=wallet.id,
        group_id=wallet.group_id,
        wallet_type=wallet.wallet_type,
        status=wallet_status,
        total_usd=total_usd,
        finished_at=observed_at,
    )
    session.add(wallet_snapshot)
    await session.flush()
    chain = ChainSnapshot(
        wallet_snapshot_id=wallet_snapshot.id,
        chain="base",
        status=chain_status,
        total_usd=total_usd,
        error_type="rpc_unavailable" if chain_status != "success" else None,
    )
    session.add(chain)
    await session.flush()
    for symbol, address, value_usd in assets or []:
        session.add(
            SnapshotBalanceSnapshot(
                chain_snapshot_id=chain.id,
                asset_symbol=symbol,
                asset_address=address,
                asset_type="erc20",
                amount=Decimal("1"),
                price_usd=value_usd,
                value_usd=value_usd,
                price_source="coingecko",
            )
        )
    await session.flush()


async def test_allocation_filters_groups_and_exposes_other(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    selected_group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Selected"},
        )
    ).json()
    other_group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Other"},
        )
    ).json()
    selected_id = await _create_wallet(
        client,
        auth_headers,
        suffix=201,
        group_id=selected_group["id"],
    )
    other_id = await _create_wallet(
        client,
        auth_headers,
        suffix=202,
        group_id=other_group["id"],
    )
    selected_wallet = await db_session.get(Wallet, selected_id)
    other_wallet = await db_session.get(Wallet, other_id)
    assert selected_wallet is not None
    assert other_wallet is not None
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    selected_wallet.address_updated_at = observed_at - timedelta(days=2)
    other_wallet.address_updated_at = observed_at - timedelta(days=2)
    await db_session.flush()
    assets = [
        (f"TOKEN{index}", f"0x{index:040x}", Decimal(str(70 - index * 10)))
        for index in range(6)
    ]
    await _add_snapshot(
        db_session,
        selected_wallet,
        observed_at=observed_at,
        total_usd=sum((value for _, _, value in assets), Decimal("0")),
        assets=assets,
    )
    await _add_snapshot(
        db_session,
        other_wallet,
        observed_at=observed_at,
        total_usd=Decimal("999"),
        assets=[("OUTSIDE", "0xffffffffffffffffffffffffffffffffffffffff", Decimal("999"))],
    )

    response = await client.get(
        f"/portfolio/allocation?mode=selection&group_id={selected_group['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == {
        "mode": "selection",
        "group_ids": [selected_group["id"]],
        "include_ungrouped": False,
    }
    assert len(body["items"]) == 6
    assert body["items"][-1]["asset_key"] == "__other__"
    assert body["items"][-1]["symbol"] == "Other"
    assert round(sum(item["share_pct"] for item in body["items"]), 2) == 100.0
    assert "OUTSIDE" not in {item["symbol"] for item in body["items"]}
    assert body["data_quality"]["state"] == "complete"


async def test_allocation_rejects_empty_selection_and_returns_empty_owned_group(
    client: AsyncClient,
    auth_headers: dict,
):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "Empty"},
        )
    ).json()

    invalid = await client.get(
        "/portfolio/allocation?mode=selection",
        headers=auth_headers,
    )
    empty = await client.get(
        f"/portfolio/allocation?mode=selection&group_id={group['id']}",
        headers=auth_headers,
    )

    assert invalid.status_code == 422
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["data_quality"]["state"] == "empty"


async def test_allocation_does_not_disclose_another_users_group(
    client: AsyncClient,
    auth_headers: dict,
):
    await client.post(
        "/auth/register",
        json={"email": "allocation-other@example.com", "password": "password12"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "allocation-other@example.com", "password": "password12"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    group = (
        await client.post(
            "/wallet-groups",
            headers=other_headers,
            json={"name": "Private allocation"},
        )
    ).json()

    response = await client.get(
        f"/portfolio/allocation?mode=selection&group_id={group['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_summary_exposes_complete_24h_value_change(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    wallet_id = await _create_wallet(client, auth_headers, suffix=203)
    wallet = await db_session.get(Wallet, wallet_id)
    assert wallet is not None
    now = datetime.now(timezone.utc)
    wallet.address_updated_at = now - timedelta(days=3)
    await db_session.flush()
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(hours=24, minutes=1),
        total_usd=Decimal("100"),
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("100"))],
    )
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(minutes=1),
        total_usd=Decimal("110"),
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("110"))],
    )

    response = await client.get("/portfolio/summary", headers=auth_headers)

    assert response.status_code == 200
    change = response.json()["change_24h"]
    assert change["status"] == "complete"
    assert change["kind"] == "value_change"
    assert Decimal(change["absolute_usd"]) == Decimal("10")
    assert change["percent"] == 10.0
    assert change["reason_codes"] == []


async def test_summary_suppresses_change_for_partial_current_snapshot(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    wallet_id = await _create_wallet(client, auth_headers, suffix=204)
    wallet = await db_session.get(Wallet, wallet_id)
    assert wallet is not None
    now = datetime.now(timezone.utc)
    wallet.address_updated_at = now - timedelta(days=3)
    await db_session.flush()
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(hours=24, minutes=1),
        total_usd=Decimal("100"),
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("100"))],
    )
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(minutes=1),
        total_usd=Decimal("40"),
        wallet_status="partial_success",
        chain_status="failed",
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("40"))],
    )

    response = await client.get("/portfolio/summary", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["change_24h"]["status"] == "incomplete"
    assert body["change_24h"]["percent"] is None
    assert "current_snapshot_partial" in body["change_24h"]["reason_codes"]
    assert len(body["data_health"]["chain_issues"]) == 1


async def test_summary_does_not_emit_percentage_for_zero_baseline(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    wallet_id = await _create_wallet(client, auth_headers, suffix=206)
    wallet = await db_session.get(Wallet, wallet_id)
    assert wallet is not None
    now = datetime.now(timezone.utc)
    wallet.address_updated_at = now - timedelta(days=3)
    await db_session.flush()
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(hours=24, minutes=1),
        total_usd=Decimal("0"),
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("0"))],
    )
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(minutes=1),
        total_usd=Decimal("10"),
        assets=[("ETH", "0x0000000000000000000000000000000000000001", Decimal("10"))],
    )

    response = await client.get("/portfolio/summary", headers=auth_headers)

    assert response.status_code == 200
    change = response.json()["change_24h"]
    assert change["status"] == "unavailable"
    assert change["percent"] is None
    assert change["reason_codes"] == ["baseline_zero"]


async def test_summary_ignores_snapshots_from_previous_address_revision(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    wallet_id = await _create_wallet(client, auth_headers, suffix=205)
    wallet = await db_session.get(Wallet, wallet_id)
    assert wallet is not None
    now = datetime.now(timezone.utc)
    wallet.address_updated_at = now - timedelta(minutes=30)
    await db_session.flush()
    await _add_snapshot(
        db_session,
        wallet,
        observed_at=now - timedelta(hours=1),
        total_usd=Decimal("500"),
        assets=[("OLD", "0x0000000000000000000000000000000000000001", Decimal("500"))],
    )

    response = await client.get("/portfolio/summary", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["total_usd"]) == Decimal("0")
    assert body["data_health"]["missing_wallets"] == 1
    assert body["change_24h"]["status"] == "unavailable"
