from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
import requests

from app.core.config import Settings
from app.metrics import (
    SNAPSHOT_JOB_CREATE,
    SNAPSHOT_SERVICE_CLIENT_REQUESTS,
    WALLET_BALANCE_SOURCE,
    WALLET_SNAPSHOT_FRESHNESS,
    observe_wallet_balance,
)
from app.services.snapshot_jobs import SnapshotServiceError, create_snapshot_job


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
