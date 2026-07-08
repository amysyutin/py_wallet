from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.db.models.snapshot_service import (
    ChainSnapshot,
    SnapshotBalanceSnapshot,
    SnapshotRun,
    WalletSnapshot,
)
from app.db.models.wallet import Wallet
from app.deps import CurrentUser, SessionDep
from app.schemas.portfolio import (
    AssetShare,
    PortfolioHistory,
    PortfolioPoint,
    PortfolioSummary,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
SNAPSHOT_READ_STATUSES = ("success", "partial_success")


async def _portfolio_history(
    current_user: CurrentUser,
    session: SessionDep,
    *,
    wallet_id: int | None,
    group_id: int | None,
    days: int,
) -> PortfolioHistory:
    if wallet_id is not None and group_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Pass either wallet_id or group_id, not both",
        )

    wallet_query = select(Wallet.id).where(Wallet.user_id == current_user.id)
    if wallet_id is not None:
        wallet = await session.scalar(
            select(Wallet).where(
                Wallet.id == wallet_id, Wallet.user_id == current_user.id
            )
        )
        if wallet is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
        wallet_query = wallet_query.where(Wallet.id == wallet_id)
    elif group_id is not None:
        wallet_query = wallet_query.where(Wallet.group_id == group_id)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    snapshot_at = func.coalesce(SnapshotRun.finished_at, SnapshotRun.created_at)
    rows = await session.execute(
        select(snapshot_at.label("snapshot_at"), WalletSnapshot.total_usd)
        .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
        .where(
            WalletSnapshot.wallet_id.in_(wallet_query),
            WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
            snapshot_at >= since,
        )
        .order_by(snapshot_at)
    )
    points = [
        PortfolioPoint(snapshot_at=r.snapshot_at, total_usd=r.total_usd) for r in rows
    ]
    return PortfolioHistory(
        wallet_id=wallet_id,
        group_id=group_id,
        days=days,
        points=points,
    )


@router.get("", response_model=PortfolioHistory, include_in_schema=False)
async def portfolio_history_legacy(
    current_user: CurrentUser,
    session: SessionDep,
    wallet_id: int | None = Query(default=None),
    group_id: int | None = Query(default=None),
    days: int = Query(30, ge=1, le=365),
) -> PortfolioHistory:
    return await _portfolio_history(
        current_user,
        session,
        wallet_id=wallet_id,
        group_id=group_id,
        days=days,
    )


@router.get("/history", response_model=PortfolioHistory)
async def portfolio_history(
    current_user: CurrentUser,
    session: SessionDep,
    wallet_id: int | None = Query(default=None),
    group_id: int | None = Query(default=None),
    days: int = Query(30, ge=1, le=365),
) -> PortfolioHistory:
    return await _portfolio_history(
        current_user,
        session,
        wallet_id=wallet_id,
        group_id=group_id,
        days=days,
    )


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    current_user: CurrentUser,
    session: SessionDep,
) -> PortfolioSummary:
    wallet_ids = select(Wallet.id).where(Wallet.user_id == current_user.id)

    # id последнего снапшота для каждого кошелька пользователя
    latest_ids = (
        select(func.max(WalletSnapshot.id))
        .where(
            WalletSnapshot.wallet_id.in_(wallet_ids),
            WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
        )
        .group_by(WalletSnapshot.wallet_id)
    )

    total = await session.scalar(
        select(func.coalesce(func.sum(WalletSnapshot.total_usd), 0)).where(
            WalletSnapshot.id.in_(latest_ids)
        )
    ) or Decimal("0")

    wallets_count = await session.scalar(
        select(func.count())
        .select_from(Wallet)
        .where(Wallet.user_id == current_user.id)
    ) or 0

    active_wallets_count = await session.scalar(
        select(func.count())
        .select_from(Wallet)
        .where(Wallet.user_id == current_user.id, Wallet.is_active.is_(True))
    ) or 0

    snapshot_at = func.coalesce(SnapshotRun.finished_at, SnapshotRun.created_at)
    last_snapshot_at = await session.scalar(
        select(func.max(snapshot_at))
        .select_from(WalletSnapshot)
        .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
        .where(WalletSnapshot.id.in_(latest_ids))
    )

    rows = await session.execute(
        select(
            SnapshotBalanceSnapshot.asset_symbol.label("symbol"),
            func.sum(SnapshotBalanceSnapshot.value_usd).label("usd"),
        )
        .join(
            ChainSnapshot,
            ChainSnapshot.id == SnapshotBalanceSnapshot.chain_snapshot_id,
        )
        .where(ChainSnapshot.wallet_snapshot_id.in_(latest_ids))
        .group_by(SnapshotBalanceSnapshot.asset_symbol)
        .order_by(func.sum(SnapshotBalanceSnapshot.value_usd).desc())
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
        wallets_count=wallets_count,
        active_wallets_count=active_wallets_count,
        last_snapshot_at=last_snapshot_at,
        top_assets=top_assets,
    )
