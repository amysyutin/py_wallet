from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.db.models.snapshot import Snapshot
from app.db.models.snapshot_service import SnapshotRun, WalletSnapshot
from app.db.models.wallet import Wallet
from app.deps import CurrentUser, SessionDep
from app.schemas.portfolio import (
    AssetShare,
    PortfolioHistory,
    PortfolioPoint,
    PortfolioSummary,
)
from app.services.wallet_view import build_wallet_balance_info

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

    wallet_query = select(Wallet).where(Wallet.user_id == current_user.id)
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
        wallet_query = wallet_query.where(
            Wallet.group_id == group_id,
            Wallet.is_active.is_(True),
        )
    else:
        wallet_query = wallet_query.where(Wallet.is_active.is_(True))

    wallets = list(await session.scalars(wallet_query.order_by(Wallet.id)))
    if wallet_id is None:
        seen_evm_addresses: set[str] = set()
        canonical_wallets: list[Wallet] = []
        for wallet in wallets:
            if wallet.wallet_type != "evm" or not wallet.address:
                canonical_wallets.append(wallet)
                continue
            normalized = wallet.address.strip().lower()
            if normalized in seen_evm_addresses:
                continue
            seen_evm_addresses.add(normalized)
            canonical_wallets.append(wallet)
        wallets = canonical_wallets

    wallet_ids = [wallet.id for wallet in wallets]

    since = datetime.now(timezone.utc) - timedelta(days=days)
    snapshot_at = func.coalesce(SnapshotRun.finished_at, SnapshotRun.created_at)
    rows = list(
        await session.execute(
            select(snapshot_at.label("snapshot_at"), WalletSnapshot.total_usd)
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(
                WalletSnapshot.wallet_id.in_(wallet_ids),
                WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
                snapshot_at >= since,
            )
            .order_by(snapshot_at)
        )
    )
    points = [
        PortfolioPoint(snapshot_at=r.snapshot_at, total_usd=r.total_usd) for r in rows
    ]

    new_wallet_ids = set(
        await session.scalars(
            select(WalletSnapshot.wallet_id)
            .where(
                WalletSnapshot.wallet_id.in_(wallet_ids),
                WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
            )
            .distinct()
        )
    )
    legacy_wallet_ids = [item for item in wallet_ids if item not in new_wallet_ids]
    if legacy_wallet_ids:
        legacy_rows = await session.execute(
            select(Snapshot.snapshot_at, Snapshot.total_usd).where(
                Snapshot.wallet_id.in_(legacy_wallet_ids),
                Snapshot.snapshot_at >= since,
            )
        )
        points.extend(
            PortfolioPoint(snapshot_at=row.snapshot_at, total_usd=row.total_usd)
            for row in legacy_rows
        )
        points.sort(key=lambda point: point.snapshot_at)
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
    # Legacy data can contain several active wallet rows for the same EVM
    # address. Treat the oldest active row as canonical so its balances are not
    # counted more than once. Manual wallets deliberately remain independent.
    normalized_address = func.lower(func.trim(Wallet.address))
    canonical_active_evm_ids = (
        select(func.min(Wallet.id))
        .where(
            Wallet.user_id == current_user.id,
            Wallet.wallet_type == "evm",
            Wallet.is_active.is_(True),
            Wallet.address.is_not(None),
        )
        .group_by(normalized_address)
    )
    wallet_ids = select(Wallet.id).where(
        Wallet.user_id == current_user.id,
        Wallet.is_active.is_(True),
        or_(
            Wallet.wallet_type != "evm",
            Wallet.id.in_(canonical_active_evm_ids),
        ),
    )
    wallets = list(
        await session.scalars(select(Wallet).where(Wallet.id.in_(wallet_ids)))
    )
    balance_info = await build_wallet_balance_info(session, wallets)
    total = sum(
        (balance_info[wallet.id].balance_usd for wallet in wallets),
        Decimal("0"),
    )

    wallets_count = (
        await session.scalar(
            select(func.count())
            .select_from(Wallet)
            .where(Wallet.user_id == current_user.id)
        )
        or 0
    )

    active_wallets_count = len(wallets)
    snapshot_dates = [
        balance_info[wallet.id].last_snapshot_at
        for wallet in wallets
        if balance_info[wallet.id].last_snapshot_at is not None
    ]
    last_snapshot_at = max(snapshot_dates) if snapshot_dates else None

    asset_totals: dict[str, Decimal] = {}
    for wallet in wallets:
        for asset in balance_info[wallet.id].assets:
            asset_totals[asset.symbol] = (
                asset_totals.get(asset.symbol, Decimal("0")) + asset.usd_value
            )
    ordered_assets = sorted(
        asset_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:5]
    top_assets = [
        AssetShare(
            symbol=symbol,
            usd_value=usd_value,
            share_pct=round(float(usd_value / total * 100), 2) if total else 0.0,
        )
        for symbol, usd_value in ordered_assets
    ]

    return PortfolioSummary(
        total_usd=total,
        wallets_count=wallets_count,
        active_wallets_count=active_wallets_count,
        last_snapshot_at=last_snapshot_at,
        top_assets=top_assets,
    )
