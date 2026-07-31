from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.metrics import MANUAL_REFRESH
from app.schemas.snapshot import SnapshotCreate, SnapshotJobRead
from app.services.snapshot_jobs import SnapshotServiceError, create_snapshot_job

router = APIRouter(prefix="/snapshots", tags=["snapshots"])
legacy_router = APIRouter(
    prefix="/snapshot", tags=["snapshot"], include_in_schema=False
)
ClientChannel = Literal["web", "telegram"]


def _bounded_channel(value: str | None) -> ClientChannel:
    return "telegram" if value == "telegram" else "web"


async def _create_snapshot_for_user(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
    client_channel: ClientChannel,
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
        outcome = "rejected" if exc.status_code < 500 else "unavailable"
        MANUAL_REFRESH.labels(
            channel=client_channel,
            scope=payload.scope_type,
            outcome=outcome,
        ).inc()
        raise HTTPException(exc.status_code, exc.detail) from exc

    MANUAL_REFRESH.labels(
        channel=client_channel,
        scope=payload.scope_type,
        outcome="already_running" if job.reused else "accepted",
    ).inc()
    return SnapshotJobRead(job_id=job.job_id, status=job.status, reused=job.reused)


@router.post(
    "",
    response_model=SnapshotJobRead,
    response_model_exclude_defaults=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_snapshot(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
    x_client_channel: Annotated[str | None, Header(alias="X-Client-Channel")] = None,
) -> SnapshotJobRead:
    return await _create_snapshot_for_user(
        payload,
        current_user,
        session,
        _bounded_channel(x_client_channel),
    )


@legacy_router.post(
    "",
    response_model=SnapshotJobRead,
    response_model_exclude_defaults=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_snapshot_legacy(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
    x_client_channel: Annotated[str | None, Header(alias="X-Client-Channel")] = None,
) -> SnapshotJobRead:
    return await _create_snapshot_for_user(
        payload,
        current_user,
        session,
        _bounded_channel(x_client_channel),
    )
