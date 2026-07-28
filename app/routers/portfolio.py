from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.db.models.snapshot import Snapshot
from app.db.models.snapshot_service import SnapshotRun, WalletSnapshot
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
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
        owned_group = await session.scalar(
            select(WalletGroup.id).where(
                WalletGroup.id == group_id,
                WalletGroup.user_id == current_user.id,
            )
        )
        if owned_group is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet group not found")
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
    if not wallet_ids:
        return PortfolioHistory(
            wallet_id=wallet_id,
            group_id=group_id,
            days=days,
            points=[],
        )

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list(
        await session.execute(
            select(
                WalletSnapshot.wallet_id,
                SnapshotRun.created_at.label("snapshot_at"),
                WalletSnapshot.total_usd,
            )
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(
                WalletSnapshot.wallet_id.in_(wallet_ids),
                WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
                SnapshotRun.created_at >= since,
            )
            .order_by(SnapshotRun.created_at, WalletSnapshot.id)
        )
    )

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
            select(Snapshot.wallet_id, Snapshot.snapshot_at, Snapshot.total_usd)
            .where(
                Snapshot.wallet_id.in_(legacy_wallet_ids),
                Snapshot.snapshot_at >= since,
            )
            .order_by(Snapshot.snapshot_at, Snapshot.id)
        )
        rows.extend(legacy_rows)

    rows.sort(key=lambda row: (row.snapshot_at, row.wallet_id))
    if wallet_id is not None:
        points = [
            PortfolioPoint(snapshot_at=row.snapshot_at, total_usd=row.total_usd)
            for row in rows
        ]
    else:
        latest_before_rank = func.row_number().over(
            partition_by=WalletSnapshot.wallet_id,
            order_by=(SnapshotRun.created_at.desc(), WalletSnapshot.id.desc()),
        )
        latest_before = (
            select(
                WalletSnapshot.wallet_id,
                WalletSnapshot.total_usd,
                latest_before_rank.label("snapshot_rank"),
            )
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(
                WalletSnapshot.wallet_id.in_(new_wallet_ids),
                WalletSnapshot.status.in_(SNAPSHOT_READ_STATUSES),
                SnapshotRun.created_at < since,
            )
            .subquery()
        )
        balance_by_wallet = {
            row.wallet_id: row.total_usd
            for row in await session.execute(
                select(latest_before.c.wallet_id, latest_before.c.total_usd).where(
                    latest_before.c.snapshot_rank == 1
                )
            )
        }

        if legacy_wallet_ids:
            legacy_before_rank = func.row_number().over(
                partition_by=Snapshot.wallet_id,
                order_by=(Snapshot.snapshot_at.desc(), Snapshot.id.desc()),
            )
            legacy_before = (
                select(
                    Snapshot.wallet_id,
                    Snapshot.total_usd,
                    legacy_before_rank.label("snapshot_rank"),
                )
                .where(
                    Snapshot.wallet_id.in_(legacy_wallet_ids),
                    Snapshot.snapshot_at < since,
                )
                .subquery()
            )
            balance_by_wallet.update(
                {
                    row.wallet_id: row.total_usd
                    for row in await session.execute(
                        select(
                            legacy_before.c.wallet_id,
                            legacy_before.c.total_usd,
                        ).where(legacy_before.c.snapshot_rank == 1)
                    )
                }
            )

        points = []
        row_index = 0
        while row_index < len(rows):
            snapshot_at = rows[row_index].snapshot_at
            while row_index < len(rows) and rows[row_index].snapshot_at == snapshot_at:
                row = rows[row_index]
                balance_by_wallet[row.wallet_id] = row.total_usd
                row_index += 1
            points.append(
                PortfolioPoint(
                    snapshot_at=snapshot_at,
                    total_usd=sum(balance_by_wallet.values(), Decimal("0")),
                )
            )

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
