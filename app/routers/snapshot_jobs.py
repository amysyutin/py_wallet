from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.db.models.snapshot_service import SnapshotRun
from app.deps import CurrentUser, SessionDep
from app.schemas.snapshot import SnapshotJobDetail

router = APIRouter(prefix="/snapshot-jobs", tags=["snapshot-jobs"])


def _to_detail(run: SnapshotRun) -> SnapshotJobDetail:
    return SnapshotJobDetail(
        job_id=run.id,
        status=run.status,
        scope_type=run.scope_type,
        wallet_id=run.wallet_id,
        group_id=None,
        trigger_type=run.trigger_type,
        created_at=run.created_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
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
    return _to_detail(run)
