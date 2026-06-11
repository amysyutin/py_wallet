from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.schemas.wallet import WalletCreate, WalletRead, WalletUpdate

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
