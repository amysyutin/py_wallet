from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.telegram import TelegramAccount
from app.db.models.user import User
from app.metrics import (
    FIRST_WALLET_ADDED,
    REGISTRATION_COMPLETED,
    SNAPSHOT_JOB_CREATE,
    SNAPSHOT_SERVICE_CLIENT_REQUESTS,
    WALLET_BALANCE_SOURCE,
    WALLET_SNAPSHOT_FRESHNESS,
    observe_wallet_balance,
)
from app.services.snapshot_jobs import (
    SnapshotJobResult,
    SnapshotServiceError,
    create_snapshot_job,
    retry_failed_snapshot_job,
)


def _counter_value(metric, **labels: str) -> float:
    return metric.labels(**labels)._value.get()


def _histogram_count(metric, **labels: str) -> float:
    return metric.labels(**labels)._sum.get() * 0 + sum(
        sample.value
        for sample in metric.labels(**labels).collect()[0].samples
        if sample.name.endswith("_count")
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret=None,
        snapshot_service_url="http://snapshot-service:8000",
    )


@patch("app.services.snapshot_jobs.requests.post")
def test_snapshot_client_success_metrics(mock_post: Mock) -> None:
    response = Mock(status_code=202)
    response.json.return_value = {"job_id": 42, "status": "pending"}
    mock_post.return_value = response
    client_labels = {
        "operation": "create_job",
        "scope": "wallet",
        "outcome": "success",
    }
    job_labels = {"trigger": "manual", "scope": "wallet", "outcome": "success"}
    client_before = _counter_value(SNAPSHOT_SERVICE_CLIENT_REQUESTS, **client_labels)
    job_before = _counter_value(SNAPSHOT_JOB_CREATE, **job_labels)

    result = create_snapshot_job(
        _settings(), user_id=7, scope_type="wallet", wallet_id=9
    )

    assert result.job_id == 42
    assert _counter_value(SNAPSHOT_SERVICE_CLIENT_REQUESTS, **client_labels) == (
        client_before + 1
    )
    assert _counter_value(SNAPSHOT_JOB_CREATE, **job_labels) == job_before + 1


@patch("app.services.snapshot_jobs.requests.post")
def test_snapshot_client_reads_reused_active_job(mock_post: Mock) -> None:
    response = Mock(status_code=200)
    response.json.return_value = {
        "job_id": 42,
        "status": "running",
        "reused": True,
    }
    mock_post.return_value = response

    result = create_snapshot_job(_settings(), user_id=7, scope_type="all")

    assert result == SnapshotJobResult(job_id=42, status="running", reused=True)


@patch("app.services.snapshot_jobs.requests.post")
def test_snapshot_client_forwards_only_bounded_activation_channel(
    mock_post: Mock,
) -> None:
    response = Mock(status_code=202)
    response.json.return_value = {"job_id": 43, "status": "pending"}
    mock_post.return_value = response

    create_snapshot_job(
        _settings(),
        user_id=7,
        scope_type="wallet",
        wallet_id=9,
        trigger_type="auto",
        activation_channel="telegram",
    )

    assert mock_post.call_args.kwargs["json"] == {
        "user_id": 7,
        "trigger_type": "auto",
        "scope_type": "wallet",
        "wallet_id": 9,
        "activation_channel": "telegram",
    }


@patch("app.services.snapshot_jobs.requests.post", side_effect=requests.Timeout())
def test_snapshot_client_timeout_metrics(_mock_post: Mock) -> None:
    client_labels = {
        "operation": "create_job",
        "scope": "all",
        "outcome": "timeout",
    }
    job_labels = {"trigger": "scheduler", "scope": "all", "outcome": "timeout"}
    client_before = _counter_value(SNAPSHOT_SERVICE_CLIENT_REQUESTS, **client_labels)
    job_before = _counter_value(SNAPSHOT_JOB_CREATE, **job_labels)

    with pytest.raises(SnapshotServiceError):
        create_snapshot_job(
            _settings(), user_id=7, scope_type="all", trigger_type="scheduler"
        )

    assert _counter_value(SNAPSHOT_SERVICE_CLIENT_REQUESTS, **client_labels) == (
        client_before + 1
    )
    assert _counter_value(SNAPSHOT_JOB_CREATE, **job_labels) == job_before + 1


@patch("app.services.snapshot_jobs.requests.post")
def test_snapshot_retry_client_reads_reused_job(mock_post: Mock) -> None:
    response = Mock(status_code=200)
    response.json.return_value = {
        "job_id": 77,
        "status": "running",
        "reused": True,
    }
    mock_post.return_value = response

    result = retry_failed_snapshot_job(_settings(), parent_job_id=42)

    assert result == SnapshotJobResult(job_id=77, status="running", reused=True)
    assert mock_post.call_args.args[0].endswith(
        "/internal/snapshot-jobs/42/retry-failed"
    )


def test_wallet_balance_source_and_freshness_metrics() -> None:
    source_labels = {"source": "latest_snapshot"}
    source_before = _counter_value(WALLET_BALANCE_SOURCE, **source_labels)
    freshness_before = _histogram_count(WALLET_SNAPSHOT_FRESHNESS, **source_labels)

    observe_wallet_balance(
        source="latest_snapshot",
        snapshot_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    assert _counter_value(WALLET_BALANCE_SOURCE, **source_labels) == source_before + 1
    assert (
        _histogram_count(WALLET_SNAPSHOT_FRESHNESS, **source_labels)
        == freshness_before + 1
    )


async def test_first_wallet_metric_uses_bounded_channel_and_counts_once(
    client,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    telegram_evm = {"channel": "telegram", "wallet_type": "evm"}
    web_manual = {"channel": "web", "wallet_type": "manual"}
    telegram_before = _counter_value(FIRST_WALLET_ADDED, **telegram_evm)
    web_before = _counter_value(FIRST_WALLET_ADDED, **web_manual)
    telegram_user = await db_session.scalar(
        select(User).where(User.email == "test@example.com")
    )
    assert telegram_user is not None
    db_session.add(
        TelegramAccount(
            user_id=telegram_user.id,
            telegram_user_id=987654321,
            first_name="Metrics",
        )
    )
    await db_session.flush()

    first = await client.post(
        "/wallets",
        headers={**auth_headers, "X-Client-Channel": "web"},
        json={
            "label": "First",
            "address": "0x00000000000000000000000000000000000000f1",
            "chain_type": "mainnet",
        },
    )
    second = await client.post(
        "/wallets",
        headers={**auth_headers, "X-Client-Channel": "web"},
        json={
            "label": "Second",
            "wallet_type": "manual",
            "chain_type": "manual",
        },
    )
    await client.post(
        "/auth/register",
        json={"email": "metric-fallback@example.com", "password": "password12"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "metric-fallback@example.com", "password": "password12"},
    )
    fallback_first = await client.post(
        "/wallets",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Client-Channel": "telegram",
        },
        json={
            "label": "Fallback",
            "wallet_type": "manual",
            "chain_type": "manual",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert fallback_first.status_code == 201
    assert _counter_value(FIRST_WALLET_ADDED, **telegram_evm) == telegram_before + 1
    assert _counter_value(FIRST_WALLET_ADDED, **web_manual) == web_before + 1

    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert (
        'py_wallet_first_wallet_added_total{channel="telegram",wallet_type="evm"}'
        in metrics.text
    )
    assert "0x00000000000000000000000000000000000000f1" not in metrics.text


async def test_email_registration_metric_ignores_caller_supplied_channel(
    client,
) -> None:
    web_labels = {"channel": "web"}
    telegram_labels = {"channel": "telegram"}
    web_before = _counter_value(REGISTRATION_COMPLETED, **web_labels)
    telegram_before = _counter_value(REGISTRATION_COMPLETED, **telegram_labels)
    payload = {"email": "registration-metric@example.com", "password": "password12"}

    created = await client.post(
        "/auth/register",
        headers={"X-Client-Channel": "telegram"},
        json=payload,
    )
    duplicate = await client.post(
        "/auth/register",
        headers={"X-Client-Channel": "telegram"},
        json=payload,
    )
    fallback = await client.post(
        "/auth/register",
        headers={"X-Client-Channel": "unbounded-client-value"},
        json={
            "email": "registration-metric-fallback@example.com",
            "password": "password12",
        },
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert fallback.status_code == 201
    assert _counter_value(REGISTRATION_COMPLETED, **telegram_labels) == telegram_before
    assert _counter_value(REGISTRATION_COMPLETED, **web_labels) == web_before + 2

    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert 'py_wallet_registration_completed_total{channel="telegram"}' in metrics.text
    assert 'channel="unbounded-client-value"' not in metrics.text
    assert "registration-metric@example.com" not in metrics.text
