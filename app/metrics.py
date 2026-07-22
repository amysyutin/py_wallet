"""Low-cardinality operational and product Prometheus metrics.

Never add wallet, user, job, request, or address identifiers as labels here.
Those values are unbounded and would make time-series cardinality grow forever.
"""

from datetime import datetime, timezone
from time import perf_counter
from typing import Awaitable, Callable

from prometheus_client import Counter, Gauge, Histogram

BUILD_INFO = Gauge(
    "py_wallet_build_info",
    "Release identity of the running py-wallet API.",
    ("version", "sha", "environment"),
)

SNAPSHOT_SERVICE_CLIENT_REQUESTS = Counter(
    "py_wallet_snapshot_service_client_requests_total",
    "Calls from py-wallet API to snapshot-service.",
    ("operation", "scope", "outcome"),
)
SNAPSHOT_SERVICE_CLIENT_DURATION = Histogram(
    "py_wallet_snapshot_service_client_request_duration_seconds",
    "Latency of calls from py-wallet API to snapshot-service.",
    ("operation", "scope", "outcome"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
SNAPSHOT_JOB_CREATE = Counter(
    "py_wallet_snapshot_job_create_total",
    "Snapshot job creation attempts by trigger, scope and outcome.",
    ("trigger", "scope", "outcome"),
)

SNAPSHOT_SCHEDULER_LAST_TICK = Gauge(
    "py_wallet_snapshot_scheduler_last_tick_timestamp_seconds",
    "Unix timestamp of the most recent scheduler tick.",
)
SNAPSHOT_SCHEDULER_TICKS = Counter(
    "py_wallet_snapshot_scheduler_ticks_total",
    "Scheduler ticks by outcome.",
    ("outcome",),
)
SNAPSHOT_SCHEDULER_JOBS = Counter(
    "py_wallet_snapshot_scheduler_jobs_total",
    "Snapshot jobs requested by the scheduler, by outcome.",
    ("outcome",),
)
SNAPSHOT_SCHEDULER_USERS = Histogram(
    "py_wallet_snapshot_scheduler_active_users",
    "Number of distinct active-wallet users seen during a scheduler tick.",
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000),
)

WALLET_BALANCE_SOURCE = Counter(
    "py_wallet_wallet_balance_source_observations_total",
    "Wallet summaries returned by persisted balance source.",
    ("source",),
)
WALLET_SNAPSHOT_FRESHNESS = Histogram(
    "py_wallet_wallet_snapshot_freshness_seconds",
    "Age of persisted snapshots returned in wallet summaries.",
    ("source",),
    buckets=(60, 300, 900, 1800, 3600, 10800, 21600, 43200, 86400, 604800),
)
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed by method, route template, and status.",
    ("method", "handler", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration by method and route template.",
    ("method", "handler"),
)


class HttpMetricsMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status_code = 500

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            handler = getattr(route, "path", "unmatched")
            method = scope.get("method", "UNKNOWN")
            HTTP_REQUESTS.labels(method, handler, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, handler).observe(
                perf_counter() - started
            )


def configure_build_info(*, version: str, sha: str, environment: str) -> None:
    """Publish immutable release identity for deployment verification."""
    BUILD_INFO.labels(version=version, sha=sha, environment=environment).set(1)


def observe_wallet_balance(*, source: str, snapshot_at: datetime | None) -> None:
    """Record the balance source and freshness exposed to an API consumer."""
    WALLET_BALANCE_SOURCE.labels(source=source).inc()
    if snapshot_at is None:
        return
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - snapshot_at).total_seconds())
    WALLET_SNAPSHOT_FRESHNESS.labels(source=source).observe(age_seconds)
