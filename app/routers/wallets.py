from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.schemas.manual_balance import ManualBalancesPut, ManualBalancesRead
from app.schemas.wallet import WalletCreate, WalletRead, WalletUpdate
from app.services.manual_balance import (
    delete_manual_balance,
    get_manual_balances,
    upsert_manual_balances,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])


async def _get_owned_wallet(
    session: SessionDep, user_id: int, wallet_id: int
) -> Wallet | None:
    return await session.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.user_id == user_id)
    )


async def _get_owned_group(
    session: SessionDep, user_id: int, group_id: int
) -> WalletGroup | None:
    return await session.scalar(
        select(WalletGroup).where(
            WalletGroup.id == group_id,
            WalletGroup.user_id == user_id,
        )
    )


async def _validate_group_id(
    session: SessionDep, user_id: int, group_id: int | None
) -> None:
    if group_id is None:
        return
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet group not found",
        )


@router.post("", response_model=WalletRead, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    payload: WalletCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> Wallet:
    await _validate_group_id(session, current_user.id, payload.group_id)

    wallet = Wallet(
        user_id=current_user.id,
        label=payload.label,
        address=payload.address,
        chain_type=payload.chain_type,
        wallet_type=payload.wallet_type,
        group_id=payload.group_id,
        notes=payload.notes,
    )
    session.add(wallet)
    await session.commit()
    await session.refresh(wallet)
    return wallet


@router.get("", response_model=list[WalletRead])
async def list_wallets(
    current_user: CurrentUser,
    session: SessionDep,
    active_only: bool = Query(default=True),
) -> list[Wallet]:
    query = select(Wallet).where(Wallet.user_id == current_user.id)
    if active_only:
        query = query.where(Wallet.is_active.is_(True))
    query = query.order_by(Wallet.id)
    result = await session.scalars(query)
    return list(result)


@router.get("/{wallet_id}", response_model=WalletRead)
async def get_wallet(
    wallet_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> Wallet:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return wallet


@router.patch("/{wallet_id}", response_model=WalletRead)
async def update_wallet(
    wallet_id: int,
    payload: WalletUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> Wallet:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")

    updates = payload.model_dump(exclude_unset=True)
    if "group_id" in updates:
        await _validate_group_id(session, current_user.id, updates["group_id"])

    for field, value in updates.items():
        setattr(wallet, field, value)

    await session.commit()
    await session.refresh(wallet)
    return wallet


@router.delete("/{wallet_id}", response_model=WalletRead)
async def delete_wallet(
    wallet_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> Wallet:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")

    if wallet.is_active:
        wallet.is_active = False
        await session.commit()
        await session.refresh(wallet)

    return wallet


@router.get("/{wallet_id}/balances", response_model=ManualBalancesRead)
async def list_wallet_balances(
    wallet_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualBalancesRead:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return await get_manual_balances(session, wallet)


@router.put("/{wallet_id}/balances", response_model=ManualBalancesRead)
async def put_wallet_balances(
    wallet_id: int,
    payload: ManualBalancesPut,
    current_user: CurrentUser,
    session: SessionDep,
) -> ManualBalancesRead:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return await upsert_manual_balances(session, wallet, payload)


@router.delete(
    "/{wallet_id}/balances/{asset_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_wallet_balance(
    wallet_id: int,
    asset_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    wallet = await _get_owned_wallet(session, current_user.id, wallet_id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return await delete_manual_balance(session, wallet, asset_id)
