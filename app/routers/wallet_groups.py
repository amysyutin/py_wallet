from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.schemas.wallet_group import (
    WalletGroupCreate,
    WalletGroupRead,
    WalletGroupUpdate,
)

router = APIRouter(prefix="/wallet-groups", tags=["wallet-groups"])


async def _get_owned_group(
    session: SessionDep, user_id: int, group_id: int
) -> WalletGroup | None:
    return await session.scalar(
        select(WalletGroup).where(
            WalletGroup.id == group_id,
            WalletGroup.user_id == user_id,
        )
    )


async def _wallets_count(session: SessionDep, group_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Wallet)
            .where(Wallet.group_id == group_id)
        )
        or 0
    )


async def _to_read(
    session: SessionDep, group: WalletGroup, wallets_count: int | None = None
) -> WalletGroupRead:
    count = wallets_count if wallets_count is not None else await _wallets_count(
        session, group.id
    )
    return WalletGroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        wallets_count=count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.post("", response_model=WalletGroupRead, status_code=status.HTTP_201_CREATED)
async def create_wallet_group(
    payload: WalletGroupCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> WalletGroupRead:
    group = WalletGroup(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order,
    )
    session.add(group)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet group with this name already exists",
        )
    await session.refresh(group)
    return await _to_read(session, group, wallets_count=0)


@router.get("", response_model=list[WalletGroupRead])
async def list_wallet_groups(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[WalletGroupRead]:
    groups = list(
        await session.scalars(
            select(WalletGroup)
            .where(WalletGroup.user_id == current_user.id)
            .order_by(WalletGroup.sort_order, WalletGroup.id)
        )
    )
    if not groups:
        return []

    counts_rows = await session.execute(
        select(Wallet.group_id, func.count())
        .where(
            Wallet.group_id.in_([g.id for g in groups]),
            Wallet.user_id == current_user.id,
        )
        .group_by(Wallet.group_id)
    )
    counts = {row[0]: row[1] for row in counts_rows}

    return [
        await _to_read(session, g, wallets_count=counts.get(g.id, 0)) for g in groups
    ]


@router.get("/{group_id}", response_model=WalletGroupRead)
async def get_wallet_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> WalletGroupRead:
    group = await _get_owned_group(session, current_user.id, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet group not found")
    return await _to_read(session, group)


@router.patch("/{group_id}", response_model=WalletGroupRead)
async def update_wallet_group(
    group_id: int,
    payload: WalletGroupUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> WalletGroupRead:
    group = await _get_owned_group(session, current_user.id, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet group not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(group, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet group with this name already exists",
        )
    await session.refresh(group)
    return await _to_read(session, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    group = await _get_owned_group(session, current_user.id, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet group not found")

    await session.delete(group)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
