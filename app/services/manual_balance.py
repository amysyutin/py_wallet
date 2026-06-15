from decimal import Decimal

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.manual_balance import ManualBalance
from app.db.models.wallet import Wallet
from app.schemas.manual_balance import (
    ManualBalanceItemRead,
    ManualBalancesPut,
    ManualBalancesRead,
)
from app.services.asset import get_or_create_manual_asset


def _value_usd(amount: Decimal, price_usd: Decimal | None) -> Decimal:
    return amount * (price_usd if price_usd is not None else Decimal("0"))


def _build_balances_read(wallet: Wallet) -> ManualBalancesRead:
    items: list[ManualBalanceItemRead] = []
    total = Decimal("0")
    for balance in wallet.manual_balances:
        asset = balance.asset
        value = _value_usd(balance.amount, balance.price_usd)
        total += value
        items.append(
            ManualBalanceItemRead(
                asset_id=asset.id,
                symbol=asset.symbol,
                chain=asset.chain,
                amount=balance.amount,
                price_usd=balance.price_usd,
                value_usd=value,
            )
        )
    return ManualBalancesRead(
        wallet_id=wallet.id,
        wallet_label=wallet.label,
        wallet_type=wallet.wallet_type,
        balances=items,
        total_usd=total,
    )


async def get_manual_balances(
    session: AsyncSession, wallet: Wallet
) -> ManualBalancesRead:
    result = await session.scalar(
        select(Wallet)
        .options(selectinload(Wallet.manual_balances).selectinload(ManualBalance.asset))
        .where(Wallet.id == wallet.id)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return _build_balances_read(result)


def _ensure_manual_wallet(wallet: Wallet) -> None:
    if wallet.wallet_type != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual balances are only allowed for manual wallets",
        )


async def upsert_manual_balances(
    session: AsyncSession,
    wallet: Wallet,
    payload: ManualBalancesPut,
) -> ManualBalancesRead:
    _ensure_manual_wallet(wallet)

    if not payload.balances:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="balances list cannot be empty",
        )

    for item in payload.balances:
        asset = await get_or_create_manual_asset(
            session, symbol=item.symbol, chain=item.chain
        )
        existing = await session.scalar(
            select(ManualBalance).where(
                ManualBalance.wallet_id == wallet.id,
                ManualBalance.asset_id == asset.id,
            )
        )
        if existing is None:
            session.add(
                ManualBalance(
                    wallet_id=wallet.id,
                    asset_id=asset.id,
                    amount=item.amount,
                    price_usd=item.price_usd,
                )
            )
        else:
            existing.amount = item.amount
            existing.price_usd = item.price_usd

    await session.commit()
    return await get_manual_balances(session, wallet)


async def delete_manual_balance(
    session: AsyncSession,
    wallet: Wallet,
    asset_id: int,
) -> Response:
    _ensure_manual_wallet(wallet)

    balance = await session.scalar(
        select(ManualBalance).where(
            ManualBalance.wallet_id == wallet.id,
            ManualBalance.asset_id == asset_id,
        )
    )
    if balance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Balance not found")

    await session.delete(balance)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
