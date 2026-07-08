from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.schemas.snapshot import SnapshotCreate, SnapshotJobRead
from app.services.snapshot_jobs import SnapshotServiceError, create_snapshot_job

router = APIRouter(prefix="/snapshots", tags=["snapshots"])
legacy_router = APIRouter(prefix="/snapshot", tags=["snapshot"], include_in_schema=False)


async def _create_snapshot_for_user(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SnapshotJobRead:
    if payload.scope_type == "wallet":
        assert payload.wallet_id is not None
        wallet = await session.scalar(
            select(Wallet).where(
                Wallet.id == payload.wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
        if wallet is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
        if not wallet.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wallet is inactive")
    elif payload.scope_type == "group":
        assert payload.group_id is not None
        group = await session.scalar(
            select(WalletGroup).where(
                WalletGroup.id == payload.group_id,
                WalletGroup.user_id == current_user.id,
            )
        )
        if group is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet group not found")

    try:
        job = await run_in_threadpool(
            create_snapshot_job,
            get_settings(),
            user_id=current_user.id,
            scope_type=payload.scope_type,
            wallet_id=payload.wallet_id,
            group_id=payload.group_id,
        )
    except SnapshotServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    return SnapshotJobRead(job_id=job.job_id, status=job.status)


@router.post(
    "",
    response_model=SnapshotJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_snapshot(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SnapshotJobRead:
    return await _create_snapshot_for_user(payload, current_user, session)


@legacy_router.post(
    "",
    response_model=SnapshotJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_snapshot_legacy(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SnapshotJobRead:
    return await _create_snapshot_for_user(payload, current_user, session)
