"""Tests for /snapshots and /snapshot-jobs endpoints."""

from datetime import datetime, timezone
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot_service import ChainSnapshot, SnapshotRun, WalletSnapshot
from app.db.models.wallet import Wallet
from app.metrics import FAILED_CHAIN_RETRY, MANUAL_REFRESH
from app.services.snapshot_jobs import SnapshotJobResult


def _counter_value(metric, **labels: str) -> float:
    return metric.labels(**labels)._value.get()


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


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=301, status="pending"),
)
async def test_post_snapshots_all_scope(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/snapshots",
        headers=auth_headers,
        json={"scope_type": "all"},
    )
    assert r.status_code == 202
    assert r.json() == {"job_id": 301, "status": "pending"}
    assert mock_create_job.call_args.kwargs["scope_type"] == "all"
    assert mock_create_job.call_args.kwargs["wallet_id"] is None
    assert mock_create_job.call_args.kwargs["group_id"] is None


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=305, status="running", reused=True),
)
async def test_post_snapshots_reuses_active_job_and_records_bounded_channel(
    _mock_create_job, client: AsyncClient, auth_headers: dict
):
    labels = {
        "channel": "telegram",
        "scope": "all",
        "outcome": "already_running",
    }
    before = _counter_value(MANUAL_REFRESH, **labels)

    response = await client.post(
        "/snapshots",
        headers={**auth_headers, "X-Client-Channel": "telegram"},
        json={"scope_type": "all"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": 305,
        "status": "running",
        "reused": True,
    }
    assert _counter_value(MANUAL_REFRESH, **labels) == before + 1


@patch("app.routers.snapshots.create_snapshot_job")
async def test_post_snapshots_refresh_metric_does_not_use_unbounded_channel(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    from app.services.snapshot_jobs import SnapshotServiceError

    mock_create_job.side_effect = SnapshotServiceError(
        502, "Snapshot service is unavailable"
    )
    labels = {"channel": "web", "scope": "all", "outcome": "unavailable"}
    before = _counter_value(MANUAL_REFRESH, **labels)

    response = await client.post(
        "/snapshots",
        headers={**auth_headers, "X-Client-Channel": "user-123"},
        json={"scope_type": "all"},
    )

    assert response.status_code == 502
    assert _counter_value(MANUAL_REFRESH, **labels) == before + 1


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=302, status="pending"),
)
async def test_post_snapshots_wallet_scope(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "ScopeWallet",
                "address": "0x00000000000000000000000000000000000000d1",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.post(
        "/snapshots",
        headers=auth_headers,
        json={"scope_type": "wallet", "wallet_id": wallet["id"]},
    )
    assert r.status_code == 202
    assert mock_create_job.call_args.kwargs["scope_type"] == "wallet"
    assert mock_create_job.call_args.kwargs["wallet_id"] == wallet["id"]


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=303, status="pending"),
)
async def test_post_snapshots_group_scope(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    group = (
        await client.post(
            "/wallet-groups",
            headers=auth_headers,
            json={"name": "SnapGroup"},
        )
    ).json()
    r = await client.post(
        "/snapshots",
        headers=auth_headers,
        json={"scope_type": "group", "group_id": group["id"]},
    )
    assert r.status_code == 202
    assert mock_create_job.call_args.kwargs["scope_type"] == "group"
    assert mock_create_job.call_args.kwargs["group_id"] == group["id"]


@patch(
    "app.routers.snapshots.create_snapshot_job",
    return_value=SnapshotJobResult(job_id=304, status="pending"),
)
async def test_post_snapshots_legacy_wallet_id_compat(
    mock_create_job, client: AsyncClient, auth_headers: dict
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "LegacyBody",
                "address": "0x00000000000000000000000000000000000000d2",
                "chain_type": "mainnet",
            },
        )
    ).json()
    r = await client.post(
        "/snapshot",
        headers=auth_headers,
        json={"wallet_id": wallet["id"]},
    )
    assert r.status_code == 202
    assert mock_create_job.call_args.kwargs["scope_type"] == "wallet"
    assert mock_create_job.call_args.kwargs["wallet_id"] == wallet["id"]


async def test_post_snapshots_group_not_found(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/snapshots",
        headers=auth_headers,
        json={"scope_type": "group", "group_id": 99999},
    )
    assert r.status_code == 404


async def test_snapshot_jobs_list_and_get(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    wallet = (
        await client.post(
            "/wallets",
            headers=auth_headers,
            json={
                "label": "Jobs",
                "address": "0x00000000000000000000000000000000000000d3",
                "chain_type": "mainnet",
            },
        )
    ).json()
    db_wallet = await db_session.get(Wallet, wallet["id"])
    assert db_wallet is not None

    run_ok = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=db_wallet.id,
        trigger_type="manual",
        scope_type="wallet",
        status="success",
        finished_at=datetime.now(timezone.utc),
    )
    run_pending = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=None,
        trigger_type="manual",
        scope_type="all",
        status="pending",
    )
    run_group = SnapshotRun(
        user_id=db_wallet.user_id,
        wallet_id=None,
        group_id=73,
        trigger_type="manual",
        scope_type="group",
        status="pending",
    )
    db_session.add_all([run_ok, run_pending, run_group])
    await db_session.flush()

    all_jobs = await client.get("/snapshot-jobs", headers=auth_headers)
    assert all_jobs.status_code == 200
    assert len(all_jobs.json()) >= 2

    filtered = await client.get("/snapshot-jobs?status=pending", headers=auth_headers)
    assert filtered.status_code == 200
    assert all(j["status"] == "pending" for j in filtered.json())
    assert any(j["job_id"] == run_pending.id for j in filtered.json())

    detail = await client.get(f"/snapshot-jobs/{run_ok.id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["job_id"] == run_ok.id
    assert body["status"] == "success"
    assert body["scope_type"] == "wallet"
    assert body["wallet_id"] == db_wallet.id

    group_detail = await client.get(
        f"/snapshot-jobs/{run_group.id}", headers=auth_headers
    )
    assert group_detail.status_code == 200
    assert group_detail.json()["scope_type"] == "group"
    assert group_detail.json()["group_id"] == 73


async def test_snapshot_jobs_filter_auto_job_by_owned_wallet(
    client: AsyncClient, db_session: AsyncSession
):
    h1 = await _register_and_login(client, "job-filter-owner@example.com")
    h2 = await _register_and_login(client, "job-filter-other@example.com")
    owner_wallet = (
        await client.post(
            "/wallets",
            headers=h1,
            json={
                "label": "Owner wallet",
                "address": "0x00000000000000000000000000000000000000e1",
                "chain_type": "mainnet",
            },
        )
    ).json()
    other_wallet = (
        await client.post(
            "/wallets",
            headers=h2,
            json={
                "label": "Other wallet",
                "address": "0x00000000000000000000000000000000000000e2",
                "chain_type": "mainnet",
            },
        )
    ).json()
    owner_db_wallet = await db_session.get(Wallet, owner_wallet["id"])
    other_db_wallet = await db_session.get(Wallet, other_wallet["id"])
    assert owner_db_wallet is not None
    assert other_db_wallet is not None

    manual_run = SnapshotRun(
        user_id=owner_db_wallet.user_id,
        wallet_id=owner_wallet["id"],
        trigger_type="manual",
        scope_type="wallet",
        status="success",
    )
    auto_run = SnapshotRun(
        user_id=owner_db_wallet.user_id,
        wallet_id=owner_wallet["id"],
        trigger_type="auto",
        scope_type="wallet",
        status="pending",
    )
    foreign_auto_run = SnapshotRun(
        user_id=other_db_wallet.user_id,
        wallet_id=other_wallet["id"],
        trigger_type="auto",
        scope_type="wallet",
        status="pending",
    )
    db_session.add_all([manual_run, auto_run, foreign_auto_run])
    await db_session.flush()

    response = await client.get(
        f"/snapshot-jobs?wallet_id={owner_wallet['id']}&trigger_type=auto&limit=1",
        headers=h1,
    )

    assert response.status_code == 200
    assert [job["job_id"] for job in response.json()] == [auto_run.id]

    hidden = await client.get(
        f"/snapshot-jobs?wallet_id={other_wallet['id']}&trigger_type=auto",
        headers=h1,
    )
    assert hidden.status_code == 200
    assert hidden.json() == []


async def test_snapshot_jobs_other_user_404(
    client: AsyncClient, db_session: AsyncSession
):
    h1 = await _register_and_login(client, "jobs-owner@example.com")
    h2 = await _register_and_login(client, "jobs-other@example.com")
    wallet = (
        await client.post(
            "/wallets",
            headers=h1,
            json={
                "label": "PrivateJob",
                "address": "0x00000000000000000000000000000000000000d4",
                "chain_type": "mainnet",
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
        status="pending",
    )
    db_session.add(run)
    await db_session.flush()

    r = await client.get(f"/snapshot-jobs/{run.id}", headers=h2)
    assert r.status_code == 404


@patch(
    "app.routers.snapshot_jobs.retry_failed_snapshot_job",
    return_value=SnapshotJobResult(job_id=402, status="pending"),
)
async def test_retry_failed_chains_is_owner_safe_and_returns_summary(
    mock_retry,
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_headers = await _register_and_login(client, "retry-owner@example.com")
    other_headers = await _register_and_login(client, "retry-other@example.com")
    owner_wallet = (
        await client.post(
            "/wallets",
            headers=owner_headers,
            json={
                "label": "Retry wallet",
                "address": "0x00000000000000000000000000000000000000f2",
                "chain_type": "mainnet",
            },
        )
    ).json()
    wallet = await db_session.get(Wallet, owner_wallet["id"])
    assert wallet is not None
    run = SnapshotRun(
        user_id=wallet.user_id,
        wallet_id=None,
        trigger_type="manual",
        scope_type="all",
        status="partial_success",
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    wallet_snapshot = WalletSnapshot(
        snapshot_run_id=run.id,
        wallet_id=wallet.id,
        wallet_type="evm",
        status="partial_success",
        total_usd=0,
    )
    db_session.add(wallet_snapshot)
    await db_session.flush()
    db_session.add_all(
        [
            ChainSnapshot(
                wallet_snapshot_id=wallet_snapshot.id,
                chain="mainnet",
                status="failed",
                total_usd=0,
                error_type="timeout",
                error_message="provider secret",
            ),
            ChainSnapshot(
                wallet_snapshot_id=wallet_snapshot.id,
                chain="base",
                status="failed",
                total_usd=0,
                error_type="connection_error",
            ),
        ]
    )
    await db_session.flush()

    detail = await client.get(f"/snapshot-jobs/{run.id}", headers=owner_headers)
    assert detail.status_code == 200
    assert detail.json()["failed_chains"] == ["base", "mainnet"]
    assert "provider secret" not in str(detail.json()["failed_chains"])

    hidden = await client.post(
        f"/snapshot-jobs/{run.id}/retry-failed",
        headers=other_headers,
    )
    assert hidden.status_code == 404
    assert mock_retry.call_count == 0

    labels = {"channel": "telegram", "outcome": "accepted"}
    before = _counter_value(FAILED_CHAIN_RETRY, **labels)
    retry = await client.post(
        f"/snapshot-jobs/{run.id}/retry-failed",
        headers={**owner_headers, "X-Client-Channel": "telegram"},
    )

    assert retry.status_code == 202
    assert retry.json() == {"job_id": 402, "status": "pending"}
    assert mock_retry.call_args.kwargs["parent_job_id"] == run.id
    assert _counter_value(FAILED_CHAIN_RETRY, **labels) == before + 1
