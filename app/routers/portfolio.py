from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.db.models.asset import Asset
from app.db.models.balance_snapshot import BalanceSnapshot
from app.db.models.snapshot import Snapshot
from app.db.models.wallet import Wallet
from app.deps import CurrentUser, SessionDep
from app.schemas.portfolio import (
    AssetShare,
    PortfolioHistory,
    PortfolioPoint,
    PortfolioSummary,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioHistory)
async def portfolio_history(
    current_user: CurrentUser,
    session: SessionDep,
    wallet_id: int = Query(...),
    days: int = Query(30, ge=1, le=365),
) -> PortfolioHistory:
    wallet = await session.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.user_id == current_user.id)
    )
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await session.execute(
        select(Snapshot.snapshot_at, Snapshot.total_usd)
        .where(Snapshot.wallet_id == wallet_id, Snapshot.snapshot_at >= since)
        .order_by(Snapshot.snapshot_at)
    )
    points = [
        PortfolioPoint(snapshot_at=r.snapshot_at, total_usd=r.total_usd) for r in rows
    ]
    return PortfolioHistory(wallet_id=wallet_id, days=days, points=points)


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    current_user: CurrentUser,
    session: SessionDep,
) -> PortfolioSummary:
    wallet_ids = select(Wallet.id).where(Wallet.user_id == current_user.id)

    # id последнего снапшота для каждого кошелька пользователя
    latest_ids = (
        select(func.max(Snapshot.id))
        .where(Snapshot.wallet_id.in_(wallet_ids))
        .group_by(Snapshot.wallet_id)
    )

    total = await session.scalar(
        select(func.coalesce(func.sum(BalanceSnapshot.usd_value), 0)).where(
            BalanceSnapshot.snapshot_id.in_(latest_ids)
        )
    ) or Decimal("0")

    wallets_count = await session.scalar(
        select(func.count())
        .select_from(Wallet)
        .where(Wallet.user_id == current_user.id)
    )

    rows = await session.execute(
        select(Asset.symbol, func.sum(BalanceSnapshot.usd_value).label("usd"))
        .join(Asset, Asset.id == BalanceSnapshot.asset_id)
        .where(BalanceSnapshot.snapshot_id.in_(latest_ids))
        .group_by(Asset.symbol)
        .order_by(func.sum(BalanceSnapshot.usd_value).desc())
        .limit(5)
    )

    top_assets = [
        AssetShare(
            symbol=r.symbol,
            usd_value=r.usd,
            share_pct=round(float(r.usd / total * 100), 2) if total else 0.0,
        )
        for r in rows
    ]

    return PortfolioSummary(
        total_usd=total,
        wallets_count=wallets_count or 0,
        top_assets=top_assets,
    )
