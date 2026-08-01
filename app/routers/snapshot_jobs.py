from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.snapshot_service import ChainSnapshot, SnapshotRun, WalletSnapshot
from app.deps import CurrentUser, SessionDep
from app.metrics import FAILED_CHAIN_RETRY
from app.schemas.snapshot import SnapshotJobDetail, SnapshotJobRead
from app.services.snapshot_jobs import (
    SnapshotServiceError,
    retry_failed_snapshot_job,
)

router = APIRouter(prefix="/snapshot-jobs", tags=["snapshot-jobs"])


ClientChannel = Literal["web", "telegram"]


def _bounded_channel(value: str | None) -> ClientChannel:
    return "telegram" if value == "telegram" else "web"


async def _failed_chains(session: SessionDep, run_id: int) -> list[str]:
    return list(
        await session.scalars(
            select(ChainSnapshot.chain)
            .join(
                WalletSnapshot,
                WalletSnapshot.id == ChainSnapshot.wallet_snapshot_id,
            )
            .where(
                WalletSnapshot.snapshot_run_id == run_id,
                ChainSnapshot.status == "failed",
            )
            .distinct()
            .order_by(ChainSnapshot.chain)
        )
    )


def _to_detail(
    run: SnapshotRun,
    *,
    failed_chains: list[str] | None = None,
) -> SnapshotJobDetail:
    return SnapshotJobDetail(
        job_id=run.id,
        status=run.status,
        scope_type=run.scope_type,
        wallet_id=run.wallet_id,
        group_id=run.group_id,
        trigger_type=run.trigger_type,
        created_at=run.created_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        failed_chains=failed_chains or [],
    )


@router.get("", response_model=list[SnapshotJobDetail])
async def list_snapshot_jobs(
    current_user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    wallet_id: int | None = Query(default=None, ge=1),
    trigger_type: str | None = Query(default=None),
) -> list[SnapshotJobDetail]:
    query = select(SnapshotRun).where(SnapshotRun.user_id == current_user.id)
    if status_filter is not None:
        query = query.where(SnapshotRun.status == status_filter)
    if wallet_id is not None:
        query = query.where(SnapshotRun.wallet_id == wallet_id)
    if trigger_type is not None:
        query = query.where(SnapshotRun.trigger_type == trigger_type)
    query = query.order_by(SnapshotRun.id.desc()).limit(limit)
    runs = list(await session.scalars(query))
    return [_to_detail(run) for run in runs]


@router.get("/{job_id}", response_model=SnapshotJobDetail)
async def get_snapshot_job(
    job_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> SnapshotJobDetail:
    run = await session.scalar(
        select(SnapshotRun).where(
            SnapshotRun.id == job_id,
            SnapshotRun.user_id == current_user.id,
        )
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot job not found")
    return _to_detail(
        run,
        failed_chains=await _failed_chains(session, run.id),
    )


@router.post(
    "/{job_id}/retry-failed",
    response_model=SnapshotJobRead,
    response_model_exclude_defaults=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failed_chains(
    job_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    x_client_channel: Annotated[str | None, Header(alias="X-Client-Channel")] = None,
) -> SnapshotJobRead:
    channel = _bounded_channel(x_client_channel)
    run = await session.scalar(
        select(SnapshotRun).where(
            SnapshotRun.id == job_id,
            SnapshotRun.user_id == current_user.id,
        )
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot job not found")
    if run.status not in {"partial_success", "failed"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Snapshot job is not ready for failed-chain retry",
        )
    if not await _failed_chains(session, run.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Snapshot job has no failed chains",
        )

    try:
        job = await run_in_threadpool(
            retry_failed_snapshot_job,
            get_settings(),
            parent_job_id=run.id,
        )
    except SnapshotServiceError as exc:
        FAILED_CHAIN_RETRY.labels(
            channel=channel,
            outcome="rejected" if exc.status_code < 500 else "unavailable",
        ).inc()
        raise HTTPException(exc.status_code, exc.detail) from exc

    FAILED_CHAIN_RETRY.labels(
        channel=channel,
        outcome="already_running" if job.reused else "accepted",
    ).inc()
    return SnapshotJobRead(
        job_id=job.job_id,
        status=job.status,
        reused=job.reused,
    )
