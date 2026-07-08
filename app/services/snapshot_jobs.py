from dataclasses import dataclass
from time import perf_counter
from typing import Any

import requests

from app.core.config import Settings
from app.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SnapshotJobResult:
    job_id: int
    status: str


class SnapshotServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _extract_error_detail(response: requests.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.text or "Snapshot service request failed"

    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
    return str(body)


def create_snapshot_job(
    settings: Settings,
    *,
    user_id: int,
    scope_type: str = "all",
    wallet_id: int | None = None,
    group_id: int | None = None,
) -> SnapshotJobResult:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "trigger_type": "manual",
        "scope_type": scope_type,
    }
    if wallet_id is not None:
        payload["wallet_id"] = wallet_id
    if group_id is not None:
        payload["group_id"] = group_id

    headers = {"Content-Type": "application/json"}
    if settings.snapshot_internal_api_token:
        headers["X-Internal-Token"] = settings.snapshot_internal_api_token

    url = f"{settings.snapshot_service_url.rstrip('/')}/internal/snapshot-jobs"
    started_at = perf_counter()
    logger.info(
        "Snapshot service request: method=POST url=%s user_id=%s scope_type=%s "
        "wallet_id=%s group_id=%s timeout=%ss token_configured=%s",
        url,
        user_id,
        scope_type,
        wallet_id,
        group_id,
        settings.snapshot_service_timeout_seconds,
        bool(settings.snapshot_internal_api_token),
    )
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=settings.snapshot_service_timeout_seconds,
        )
    except requests.RequestException as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.exception(
            "Snapshot service request failed: method=POST url=%s elapsed_ms=%s "
            "error_type=%s",
            url,
            elapsed_ms,
            type(exc).__name__,
        )
        raise SnapshotServiceError(502, "Snapshot service is unavailable") from exc

    elapsed_ms = int((perf_counter() - started_at) * 1000)
    if 200 <= response.status_code < 300:
        logger.info(
            "Snapshot service response: method=POST url=%s status_code=%s "
            "elapsed_ms=%s",
            url,
            response.status_code,
            elapsed_ms,
        )
    else:
        logger.warning(
            "Snapshot service response error: method=POST url=%s status_code=%s "
            "elapsed_ms=%s detail=%s",
            url,
            response.status_code,
            elapsed_ms,
            _extract_error_detail(response),
        )

    if response.status_code == 401:
        raise SnapshotServiceError(502, "Snapshot service authentication failed")
    if response.status_code == 422:
        raise SnapshotServiceError(422, _extract_error_detail(response))
    if response.status_code >= 500:
        raise SnapshotServiceError(502, "Snapshot service is unavailable")
    if not 200 <= response.status_code < 300:
        raise SnapshotServiceError(502, "Unexpected snapshot service response")

    try:
        data = response.json()
        job_id = int(data["job_id"])
        job_status = str(data["status"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotServiceError(502, "Unexpected snapshot service response") from exc

    return SnapshotJobResult(job_id=job_id, status=job_status)
