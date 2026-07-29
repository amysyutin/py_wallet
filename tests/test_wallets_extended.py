"""Tests for extended wallet CRUD and migration backfill behavior."""

from unittest.mock import ANY, AsyncMock, Mock, call, patch

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.db.models.user import User
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.models import PortfolioSummary
from app.services.snapshot_jobs import SnapshotJobResult


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
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["wallet_type"] == "evm"
    assert data["chain_type"] == "all"
    assert data["is_active"] is True
    assert data["group_id"] is None


async def test_create_wallet_supports_bigint_user_id(
    client: AsyncClient, db_session: AsyncSession
):
    user_id = 2**31
    db_session.add(
        User(
            id=user_id,
            email="bigint-wallet-user@example.com",
            auth_hash=hash_password("password12"),
        )
    )
    await db_session.flush()

    response = await client.post(
        "/wallets",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
        json={
            "label": "BIGINT owner",
            "wallet_type": "manual",
            "chain_type": "manual",
        },
    )

    assert response.status_code == 201
    assert response.json()["label"] == "BIGINT owner"


async def test_create_wallet_starts_auto_snapshot_when_explicitly_enabled(
    client: AsyncClient, auth_headers: dict
):
    settings = Settings(
        _env_file=None,
        app_env="test",
        jwt_secret=None,
        snapshot_auto_on_wallet_create=True,
        snapshot_scheduler_enabled=False,
    )
    scheduled = []
    create_snapshot_job = Mock(
        return_value=SnapshotJobResult(job_id=123, status="pending")
    )

    with (
        patch("app.routers.wallets.get_settings", return_value=settings),
        patch("app.routers.wallets.create_snapshot_job", create_snapshot_job),
        patch(
            "app.routers.wallets.asyncio.create_task",
            side_effect=lambda coroutine: scheduled.append(coroutine),
        ),
    ):
        response = await client.post(
            "/wallets",
            headers={**auth_headers, "X-Client-Channel": "telegram"},
            json={
                "label": "Auto snapshot",
                "address": "0x0000000000000000000000000000000000000012",
                "chain_type": "mainnet",
            },
        )
        repeat = await client.post(
            "/wallets",
            headers={**auth_headers, "X-Client-Channel": "web"},
            json={
                "label": "Repeat auto snapshot",
                "address": "0x0000000000000000000000000000000000000013",
                "chain_type": "mainnet",
            },
        )
        assert response.status_code == 201
        assert repeat.status_code == 201
        assert len(scheduled) == 2
        for coroutine in scheduled:
            await coroutine
        assert create_snapshot_job.call_args_list == [
            call(
                settings,
                user_id=ANY,
                scope_type="wallet",
                wallet_id=response.json()["id"],
                trigger_type="auto",
                activation_channel="web",
            ),
            call(
                settings,
                user_id=ANY,
                scope_type="wallet",
                wallet_id=repeat.json()["id"],
                trigger_type="auto",
                activation_channel=None,
            ),
        ]


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
            "address": "0x0000000000000000000000000000000000000003",
            "chain_type": "manual",
        },
    )
    assert r.status_code == 422


async def test_create_wallet_foreign_group_404(client: AsyncClient):
    h1 = await _register_and_login(client, "w-owner@example.com")
    h2 = await _register_and_login(client, "w-other@example.com")
    group = (
        await client.post("/wallet-groups", headers=h1, json={"name": "Private"})
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


async def test_patch_wallet_network_fields(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Network",
                "address": "0x0000000000000000000000000000000000000007",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={
            "address": "0x000000000000000000000000000000000000ffff",
            "chain_type": "base",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["address"] == "0x000000000000000000000000000000000000ffff"
    assert data["chain_type"] == "base"


async def test_patch_wallet_chain_type_only(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "ChainOnly",
                "address": "0x00000000000000000000000000000000000000aa",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"chain_type": "arbitrum"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chain_type"] == "arbitrum"
    assert data["address"] == wallet["address"]


async def test_patch_wallet_invalid_chain_type(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "BadChain",
                "address": "0x00000000000000000000000000000000000000ab",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"chain_type": "unknown"},
    )
    assert r.status_code == 422


async def test_patch_evm_wallet_cannot_clear_address(
    client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "NoClear",
                "address": "0x00000000000000000000000000000000000000ac",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"address": None},
    )
    assert r.status_code == 422


async def test_patch_wallet_rejects_null_required_fields(
    client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Required",
                "address": "0x00000000000000000000000000000000000000ad",
                "chain_type": "mainnet",
            },
        )
    ).json()

    for payload in ({"label": None}, {"chain_type": None}, {"is_active": None}):
        response = await client.patch(
            f"/wallets/{wallet['id']}",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 422


async def test_patch_manual_wallet_cannot_change_chain_type(
    client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Manual",
                "wallet_type": "manual",
                "chain_type": "manual",
            },
        )
    ).json()
    r = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"chain_type": "mainnet"},
    )
    assert r.status_code == 422


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
        json={"wallet_type": "manual"},
    )
    assert r.status_code == 422


@patch("app.routers.wallets.lookup_live_assets", new_callable=AsyncMock)
async def test_get_wallet_assets_evm(
    mock_live_assets, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Assets",
                "address": "0x00000000000000000000000000000000000000ad",
                "chain_type": "mainnet",
            },
        )
    ).json()
    mock_live_assets.return_value = PortfolioSummary(
        address=wallet["address"],
        chains=[],
        total_usd=12345.67,
    )

    r = await client.get(f"/wallets/{wallet['id']}/assets", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["address"] == wallet["address"]
    assert data["total_usd"] == 12345.67
    mock_live_assets.assert_awaited_once_with(wallet["address"])


@patch("app.routers.wallets.lookup_live_assets", new_callable=AsyncMock)
async def test_get_wallet_assets_prefers_latest_readable_snapshot(
    mock_live_assets,
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    from datetime import timedelta
    from decimal import Decimal

    from app.db.models.snapshot_service import (
        ChainSnapshot,
        SnapshotBalanceSnapshot,
        SnapshotRun,
        WalletSnapshot,
    )

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Persisted assets",
                "address": "0x00000000000000000000000000000000000000b1",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    snapshot_at = db_wallet.address_updated_at + timedelta(seconds=1)

    readable_run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="partial_success",
        created_at=snapshot_at,
        finished_at=snapshot_at,
    )
    db_session.add(readable_run)
    await db_session.flush()
    readable_snapshot = WalletSnapshot(
        snapshot_run_id=readable_run.id,
        wallet_id=db_wallet.id,
        wallet_type="evm",
        status="partial_success",
        total_usd=Decimal("83"),
    )
    db_session.add(readable_snapshot)
    await db_session.flush()
    mainnet = ChainSnapshot(
        wallet_snapshot_id=readable_snapshot.id,
        chain="mainnet",
        status="success",
        total_usd=Decimal("83"),
    )
    base = ChainSnapshot(
        wallet_snapshot_id=readable_snapshot.id,
        chain="base",
        status="failed",
        total_usd=Decimal("0"),
        error_type="rpc_error",
        error_message="RPC request failed",
    )
    db_session.add_all([mainnet, base])
    await db_session.flush()
    db_session.add_all(
        [
            SnapshotBalanceSnapshot(
                chain_snapshot_id=mainnet.id,
                asset_symbol="ETH",
                amount=Decimal("0.5"),
                price_usd=Decimal("150"),
                value_usd=Decimal("75"),
                price_source="test",
            ),
            SnapshotBalanceSnapshot(
                chain_snapshot_id=mainnet.id,
                asset_symbol="USDC",
                amount=Decimal("5"),
                price_usd=Decimal("1"),
                value_usd=Decimal("5"),
                price_source="test",
            ),
            SnapshotBalanceSnapshot(
                chain_snapshot_id=mainnet.id,
                asset_symbol="LINK",
                amount=Decimal("1"),
                price_usd=Decimal("3"),
                value_usd=Decimal("3"),
                price_source="test",
            ),
        ]
    )

    failed_run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="failed",
        finished_at=snapshot_at + timedelta(seconds=1),
    )
    db_session.add(failed_run)
    await db_session.flush()
    db_session.add(
        WalletSnapshot(
            snapshot_run_id=failed_run.id,
            wallet_id=db_wallet.id,
            wallet_type="evm",
            status="failed",
            total_usd=Decimal("999"),
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/wallets/{wallet['id']}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["address"] == wallet["address"]
    assert data["total_usd"] == 83.0
    assert [chain["chain"] for chain in data["chains"]] == ["mainnet", "base"]
    assert data["chains"][0]["native_amount"] == 0.5
    assert data["chains"][0]["usdc_amount"] == 5.0
    assert data["chains"][0]["tokens"] == [
        {"symbol": "LINK", "amount": 1.0, "usd": 3.0}
    ]
    assert data["chains"][1]["status"] == "failed"
    assert data["chains"][1]["error_type"] == "rpc_error"
    assert data["chains"][1]["error_message"] == "Snapshot collection failed"
    mock_live_assets.assert_not_awaited()


@patch("app.routers.wallets.lookup_live_assets", new_callable=AsyncMock)
async def test_get_wallet_assets_prefers_newer_started_run_when_old_run_finishes_later(
    mock_live_assets,
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    from datetime import timedelta
    from decimal import Decimal

    from app.db.models.snapshot_service import SnapshotRun, WalletSnapshot

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Out-of-order runs",
                "address": "0x00000000000000000000000000000000000000b5",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    first_started = db_wallet.address_updated_at + timedelta(seconds=1)
    second_started = first_started + timedelta(seconds=5)
    old_run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        created_at=first_started,
        finished_at=second_started + timedelta(seconds=10),
    )
    new_run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        created_at=second_started,
        finished_at=second_started + timedelta(seconds=1),
    )
    db_session.add_all([old_run, new_run])
    await db_session.flush()
    db_session.add_all(
        [
            WalletSnapshot(
                snapshot_run_id=old_run.id,
                wallet_id=db_wallet.id,
                wallet_type="evm",
                status="success",
                total_usd=Decimal("100"),
            ),
            WalletSnapshot(
                snapshot_run_id=new_run.id,
                wallet_id=db_wallet.id,
                wallet_type="evm",
                status="success",
                total_usd=Decimal("200"),
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        f"/wallets/{wallet['id']}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["total_usd"] == 200.0
    mock_live_assets.assert_not_awaited()


@patch("app.routers.wallets.lookup_live_assets", new_callable=AsyncMock)
async def test_get_wallet_assets_ignores_snapshot_before_wallet_update(
    mock_live_assets,
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    from datetime import timedelta
    from decimal import Decimal

    from app.db.models.snapshot_service import SnapshotRun, WalletSnapshot

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Changed address",
                "address": "0x00000000000000000000000000000000000000b2",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    run_started_at = db_wallet.address_updated_at + timedelta(seconds=1)
    address_changed_at = run_started_at + timedelta(seconds=1)
    run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        created_at=run_started_at,
        finished_at=address_changed_at + timedelta(seconds=1),
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        WalletSnapshot(
            snapshot_run_id=run.id,
            wallet_id=db_wallet.id,
            wallet_type="evm",
            status="success",
            total_usd=Decimal("50"),
        )
    )
    await db_session.flush()

    new_address = "0x00000000000000000000000000000000000000b3"
    db_wallet.address = new_address
    db_wallet.address_updated_at = address_changed_at
    db_wallet.updated_at = address_changed_at
    await db_session.flush()
    mock_live_assets.return_value = PortfolioSummary(
        address=new_address,
        chains=[],
        total_usd=10,
    )

    response = await client.get(
        f"/wallets/{wallet['id']}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["address"] == new_address
    assert response.json()["total_usd"] == 10.0
    mock_live_assets.assert_awaited_once_with(new_address)


@patch("app.routers.wallets.lookup_live_assets", new_callable=AsyncMock)
async def test_get_wallet_assets_keeps_zero_snapshot_after_metadata_update(
    mock_live_assets,
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    from datetime import timedelta
    from decimal import Decimal

    from app.db.models.snapshot_service import (
        ChainSnapshot,
        SnapshotRun,
        WalletSnapshot,
    )

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Empty snapshot",
                "address": "0x00000000000000000000000000000000000000b4",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    snapshot_at = db_wallet.address_updated_at + timedelta(seconds=1)
    run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        created_at=snapshot_at,
        finished_at=snapshot_at,
    )
    db_session.add(run)
    await db_session.flush()
    snapshot = WalletSnapshot(
        snapshot_run_id=run.id,
        wallet_id=db_wallet.id,
        wallet_type="evm",
        status="success",
        total_usd=Decimal("0"),
    )
    db_session.add(snapshot)
    await db_session.flush()
    db_session.add(
        ChainSnapshot(
            wallet_snapshot_id=snapshot.id,
            chain="mainnet",
            status="success",
            total_usd=Decimal("0"),
        )
    )
    await db_session.flush()

    metadata_update = await client.patch(
        f"/wallets/{wallet['id']}",
        headers=auth_headers,
        json={"label": "Renamed empty snapshot", "notes": "metadata only"},
    )
    assert metadata_update.status_code == 200

    response = await client.get(
        f"/wallets/{wallet['id']}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["total_usd"] == 0.0
    assert response.json()["chains"][0]["native_amount"] == 0.0
    mock_live_assets.assert_not_awaited()


async def test_get_wallet_assets_manual_wallet_400(
    client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Manual",
                "wallet_type": "manual",
                "chain_type": "manual",
            },
        )
    ).json()
    r = await client.get(f"/wallets/{wallet['id']}/assets", headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["detail"] == "Multi-chain assets are available for EVM wallets only"


async def test_get_wallet_assets_other_user_404(client: AsyncClient):
    h1 = await _register_and_login(client, "w-assets-owner@example.com")
    h2 = await _register_and_login(client, "w-assets-other@example.com")
    wallet = (
        await client.post(
            "/wallets",
            headers=h1,
            json={
                "label": "Private",
                "address": "0x00000000000000000000000000000000000000ae",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.get(f"/wallets/{wallet['id']}/assets", headers=h2)
    assert r.status_code == 404


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
    assert (
        await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    ).status_code == 200
    r = await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False


async def test_list_wallets_active_only_default(
    client: AsyncClient, auth_headers: dict
):
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


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=123, status="pending"),
)
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


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=124, status="pending"),
)
async def test_snapshot_all_scope_creates_job(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    _active = (
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
    assert r.status_code == 202
    assert r.json() == {"job_id": 124, "status": "pending"}
    assert mock_create_job.call_args.kwargs["wallet_id"] is None


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=125, status="pending"),
)
async def test_snapshot_wallet_scope_creates_job(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "MultiChainSnap",
                "address": "0x00000000000000000000000000000000000000af",
                "chain_type": "mainnet",
            },
        )
    ).json()

    r = await client.post(
        "/snapshot", headers=auth_headers, json={"wallet_id": wallet["id"]}
    )

    assert r.status_code == 202
    assert r.json() == {"job_id": 125, "status": "pending"}
    assert mock_create_job.call_args.kwargs["wallet_id"] == wallet["id"]


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
        text("""
            UPDATE wallets w
            SET group_id = wg.id
            FROM wallet_groups wg
            WHERE wg.user_id = w.user_id
              AND wg.name = 'Default'
              AND w.id = :wallet_id
            """),
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


async def test_list_wallets_summary_fields(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.db.models.snapshot_service import (
        ChainSnapshot,
        SnapshotBalanceSnapshot,
        SnapshotRun,
        WalletSnapshot,
    )

    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "SummaryGroup"},
        )
    ).json()
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "WithSnap",
                "address": "0x00000000000000000000000000000000000000c1",
                "chain_type": "mainnet",
                "group_id": group["id"],
            },
        )
    ).json()

    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    ws = WalletSnapshot(
        snapshot_run_id=run.id,
        wallet_id=db_wallet.id,
        wallet_type="evm",
        status="success",
        total_usd=Decimal("150"),
    )
    db_session.add(ws)
    await db_session.flush()
    cs = ChainSnapshot(
        wallet_snapshot_id=ws.id,
        chain="mainnet",
        status="success",
        total_usd=Decimal("150"),
    )
    db_session.add(cs)
    await db_session.flush()
    db_session.add(
        SnapshotBalanceSnapshot(
            chain_snapshot_id=cs.id,
            asset_symbol="ETH",
            amount=Decimal("0.5"),
            price_usd=Decimal("300"),
            value_usd=Decimal("150"),
            price_source="test",
        )
    )
    await db_session.flush()

    lst = await client.get("/wallets", headers=auth_headers)
    assert lst.status_code == 200
    item = next(w for w in lst.json() if w["id"] == wallet["id"])
    assert Decimal(item["balance_usd"]) == Decimal("150")
    assert item["balance_source"] == "latest_snapshot"
    assert item["group_name"] == "SummaryGroup"
    assert item["balances_count"] == 1
    assert item["top_assets"][0]["symbol"] == "ETH"
    assert item["last_snapshot_at"] is not None


async def test_list_wallets_filters(client: AsyncClient, auth_headers: dict):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "FilterGroup"},
        )
    ).json()
    evm = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "EVMFilter",
                "address": "0x00000000000000000000000000000000000000c2",
                "chain_type": "base",
                "group_id": group["id"],
            },
        )
    ).json()
    await client.post(
        "/wallets",
        headers=auth_headers,
        json={
            "label": "ManualFilter",
            "wallet_type": "manual",
            "chain_type": "manual",
        },
    )

    by_group = (
        await client.get(f"/wallets?group_id={group['id']}", headers=auth_headers)
    ).json()
    assert [w["id"] for w in by_group] == [evm["id"]]

    by_type = (
        await client.get("/wallets?wallet_type=manual", headers=auth_headers)
    ).json()
    assert all(w["wallet_type"] == "manual" for w in by_type)

    by_chain = (
        await client.get("/wallets?chain_type=base", headers=auth_headers)
    ).json()
    assert [w["id"] for w in by_chain] == [evm["id"]]


async def test_wallet_list_and_detail_fall_back_to_latest_legacy_snapshot(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from app.db.models.asset import Asset
    from app.db.models.balance_snapshot import BalanceSnapshot
    from app.db.models.snapshot import Snapshot

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Legacy snapshot",
                "address": "0x00000000000000000000000000000000000000c6",
                "chain_type": "mainnet",
            },
        )
    ).json()
    asset = Asset(
        symbol="ETH",
        name="Ethereum",
        contract_address=None,
        chain="mainnet",
        decimals=18,
    )
    db_session.add(asset)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    old_snapshot = Snapshot(
        wallet_id=wallet["id"],
        snapshot_at=now - timedelta(hours=1),
        total_usd=Decimal("10"),
    )
    latest_snapshot = Snapshot(
        wallet_id=wallet["id"],
        snapshot_at=now,
        total_usd=Decimal("75"),
    )
    db_session.add_all([old_snapshot, latest_snapshot])
    await db_session.flush()
    db_session.add_all(
        [
            BalanceSnapshot(
                snapshot_id=old_snapshot.id,
                asset_id=asset.id,
                amount=Decimal("0.1"),
                usd_value=Decimal("10"),
            ),
            BalanceSnapshot(
                snapshot_id=latest_snapshot.id,
                asset_id=asset.id,
                amount=Decimal("0.5"),
                usd_value=Decimal("75"),
            ),
        ]
    )
    await db_session.flush()

    wallets = await client.get("/wallets", headers=auth_headers)
    assert wallets.status_code == 200
    item = next(item for item in wallets.json() if item["id"] == wallet["id"])
    assert item["balance_source"] == "latest_snapshot"
    assert Decimal(item["balance_usd"]) == Decimal("75")
    assert item["balances_count"] == 1
    assert item["top_assets"][0]["symbol"] == "ETH"
    assert Decimal(item["top_assets"][0]["amount"]) == Decimal("0.5")
    assert Decimal(item["top_assets"][0]["usd_value"]) == Decimal("75")
    assert item["last_snapshot_at"] is not None

    summary = await client.get(f"/wallets/{wallet['id']}/summary", headers=auth_headers)
    assert summary.status_code == 200
    detail = summary.json()
    assert Decimal(detail["balance_usd"]) == Decimal("75")
    assert detail["last_snapshot_at"] is not None
    assert detail["assets"][0]["symbol"] == "ETH"
    assert Decimal(detail["assets"][0]["amount"]) == Decimal("0.5")
    assert Decimal(detail["assets"][0]["usd_value"]) == Decimal("75")
    assert Decimal(detail["assets"][0]["price_usd"]) == Decimal("150")

    portfolio = await client.get("/portfolio/summary", headers=auth_headers)
    assert portfolio.status_code == 200
    portfolio_data = portfolio.json()
    assert Decimal(portfolio_data["total_usd"]) == Decimal("75")
    assert portfolio_data["active_wallets_count"] == 1
    assert portfolio_data["top_assets"][0]["symbol"] == "ETH"

    history = await client.get("/portfolio/history?days=30", headers=auth_headers)
    assert history.status_code == 200
    assert [Decimal(point["total_usd"]) for point in history.json()["points"]] == [
        Decimal("10"),
        Decimal("75"),
    ]


async def test_wallet_summary_and_snapshots(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.db.models.snapshot_service import (
        ChainSnapshot,
        SnapshotBalanceSnapshot,
        SnapshotRun,
        WalletSnapshot,
    )

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Detail",
                "address": "0x00000000000000000000000000000000000000c3",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None
    now = datetime.now(timezone.utc)
    run = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        finished_at=now,
    )
    db_session.add(run)
    await db_session.flush()
    ws = WalletSnapshot(
        snapshot_run_id=run.id,
        wallet_id=db_wallet.id,
        wallet_type="evm",
        status="success",
        total_usd=Decimal("80"),
    )
    db_session.add(ws)
    await db_session.flush()
    cs = ChainSnapshot(
        wallet_snapshot_id=ws.id,
        chain="mainnet",
        status="success",
        total_usd=Decimal("80"),
    )
    db_session.add(cs)
    await db_session.flush()
    db_session.add(
        SnapshotBalanceSnapshot(
            chain_snapshot_id=cs.id,
            asset_symbol="USDC",
            amount=Decimal("80"),
            price_usd=Decimal("1"),
            value_usd=Decimal("80"),
            price_source="test",
        )
    )
    await db_session.flush()

    summary = await client.get(f"/wallets/{wallet['id']}/summary", headers=auth_headers)
    assert summary.status_code == 200
    data = summary.json()
    assert data["wallet"]["id"] == wallet["id"]
    assert Decimal(data["balance_usd"]) == Decimal("80")
    assert data["assets"][0]["symbol"] == "USDC"
    assert data["assets"][0]["chain"] == "mainnet"

    snaps = await client.get(f"/wallets/{wallet['id']}/snapshots", headers=auth_headers)
    assert snaps.status_code == 200
    assert len(snaps.json()) == 1
    assert Decimal(snaps.json()[0]["total_usd"]) == Decimal("80")


async def test_restore_wallet(client: AsyncClient, auth_headers: dict):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "RestoreMe",
                "address": "0x00000000000000000000000000000000000000c4",
                "chain_type": "mainnet",
            },
        )
    ).json()
    await client.delete(f"/wallets/{wallet['id']}", headers=auth_headers)
    r = await client.post(f"/wallets/{wallet['id']}/restore", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is True


async def test_manual_wallet_summary_fallback(client: AsyncClient, auth_headers: dict):
    from decimal import Decimal

    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "ManualSum",
                "wallet_type": "manual",
                "chain_type": "manual",
            },
        )
    ).json()
    await client.put(
        f"/wallets/{wallet['id']}/balances",
        headers=auth_headers,
        json={
            "balances": [
                {"symbol": "BTC", "amount": "2", "price_usd": "10000"},
            ]
        },
    )
    lst = (await client.get("/wallets", headers=auth_headers)).json()
    item = next(w for w in lst if w["id"] == wallet["id"])
    assert item["balance_source"] == "manual"
    assert Decimal(item["balance_usd"]) == Decimal("20000")
    assert item["top_assets"][0]["symbol"] == "BTC"


@patch(
    "app.routers.wallets.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=200, status="pending"),
)
async def test_post_wallet_snapshots_shortcut(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "SnapShortcut",
                "address": "0x00000000000000000000000000000000000000c5",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.post(f"/wallets/{wallet['id']}/snapshots", headers=auth_headers)
    assert r.status_code == 202
    assert r.json() == {"job_id": 200, "status": "pending"}
    assert mock_create_job.call_args.kwargs["scope_type"] == "wallet"
    assert mock_create_job.call_args.kwargs["wallet_id"] == wallet["id"]
