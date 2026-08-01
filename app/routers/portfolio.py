from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.db.models.asset import Asset
from app.db.models.balance_snapshot import BalanceSnapshot
from app.db.models.snapshot import Snapshot
from app.core.config import get_settings
from app.db.models.snapshot_service import (
    ChainSnapshot,
    SnapshotBalanceSnapshot,
    SnapshotRun,
    WalletSnapshot,
)
from app.db.models.wallet import Wallet
from app.db.models.wallet_group import WalletGroup
from app.deps import CurrentUser, SessionDep
from app.schemas.portfolio import (
    AssetShare,
    AllocationAssetShare,
    PortfolioAllocation,
    PortfolioAllocationQuality,
    PortfolioAllScope,
    PortfolioChainIssue,
    PortfolioDataHealth,
    PortfolioHistory,
    PortfolioPoint,
    PortfolioPriceQuality,
    PortfolioSelectionScope,
    PortfolioSummary,
    PortfolioValueChange24h,
)
from app.services.wallet_view import build_wallet_balance_info

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
HISTORY_READ_STATUSES = ("success",)
ACTIVE_SNAPSHOT_STATUSES = ("pending", "running")
KNOWN_PRICE_SOURCES = frozenset({"coingecko", "manual", "static_dev"})
PRICE_SOURCE_ORDER = ("coingecko", "manual", "static_dev", "unknown")
ALLOCATION_VISIBLE_ASSETS = 5


def _snapshot_observed_at():
    return func.coalesce(
        WalletSnapshot.finished_at,
        SnapshotRun.finished_at,
        SnapshotRun.created_at,
    )


async def _active_canonical_wallets(
    session: SessionDep,
    *,
    user_id: int,
    group_ids: list[int] | None = None,
    include_ungrouped: bool = True,
) -> list[Wallet]:
    normalized_address = func.lower(func.trim(Wallet.address))
    canonical_active_evm_ids = (
        select(func.min(Wallet.id))
        .where(
            Wallet.user_id == user_id,
            Wallet.wallet_type == "evm",
            Wallet.is_active.is_(True),
            Wallet.address.is_not(None),
        )
        .group_by(normalized_address)
    )
    query = select(Wallet).where(
        Wallet.user_id == user_id,
        Wallet.is_active.is_(True),
        or_(
            Wallet.wallet_type != "evm",
            Wallet.id.in_(canonical_active_evm_ids),
        ),
    )
    if group_ids is not None:
        scope_filters = []
        if group_ids:
            scope_filters.append(Wallet.group_id.in_(group_ids))
        if include_ungrouped:
            scope_filters.append(Wallet.group_id.is_(None))
        query = query.where(or_(*scope_filters))
    return list(await session.scalars(query.order_by(Wallet.id)))


def _portfolio_freshness(
    as_of: datetime | None,
    *,
    fresh_seconds: int,
    stale_seconds: int,
) -> str:
    if as_of is None:
        return "unknown"
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())
    if age_seconds <= fresh_seconds:
        return "fresh"
    if age_seconds <= stale_seconds:
        return "aging"
    return "stale"


def _portfolio_price_quality(
    observations: list[tuple[Decimal, Decimal | None, str | None]],
) -> PortfolioPriceQuality:
    relevant = [
        (amount, price_usd, source)
        for amount, price_usd, source in observations
        if amount != Decimal("0")
    ]
    sources = {
        source if source in KNOWN_PRICE_SOURCES else "unknown"
        for _, _, source in relevant
    }
    assets_priced = sum(price_usd is not None for _, price_usd, _ in relevant)
    assets_total = len(relevant)

    if assets_total == 0:
        quality_state = "unknown"
    elif assets_priced < assets_total:
        quality_state = "incomplete"
    elif "static_dev" in sources:
        quality_state = "estimated"
    elif "unknown" in sources:
        quality_state = "unknown"
    else:
        quality_state = "complete"

    return PortfolioPriceQuality(
        state=quality_state,
        sources=[source for source in PRICE_SOURCE_ORDER if source in sources],
        assets_priced=assets_priced,
        assets_total=assets_total,
    )


def _allocation_asset_key(
    *,
    chain: str,
    symbol: str,
    asset_address: str | None,
    asset_type: str | None,
) -> str:
    normalized_type = (asset_type or "").lower()
    if normalized_type == "erc20" and asset_address:
        return f"evm:{chain.lower()}:{asset_address.strip().lower()}"
    if normalized_type == "manual" or chain.lower() == "manual":
        return f"manual:{symbol.upper()}"
    if normalized_type == "native" or not asset_address:
        return f"native:{chain.lower()}:{symbol.upper()}"
    return f"{normalized_type or 'asset'}:{chain.lower()}:{asset_address.lower()}"


def _allocation_quality(
    observations: list[tuple[Decimal, Decimal | None, str | None]],
) -> PortfolioAllocationQuality:
    if not observations:
        return PortfolioAllocationQuality(
            state="empty",
            sources=[],
            assets_priced=0,
            assets_total=0,
        )
    quality = _portfolio_price_quality(observations)
    return PortfolioAllocationQuality(**quality.model_dump())


async def _allocation_for_wallets(
    session: SessionDep,
    wallets: list[Wallet],
    *,
    scope: PortfolioAllScope | PortfolioSelectionScope,
) -> PortfolioAllocation:
    balance_info = await build_wallet_balance_info(session, wallets)
    asset_totals: dict[str, tuple[str, Decimal]] = {}
    observations: list[tuple[Decimal, Decimal | None, str | None]] = []

    def add_asset(
        *,
        key: str,
        symbol: str,
        amount: Decimal,
        value_usd: Decimal,
        price_usd: Decimal | None,
        price_source: str | None,
    ) -> None:
        existing_symbol, existing_value = asset_totals.get(key, (symbol, Decimal("0")))
        asset_totals[key] = (existing_symbol, existing_value + value_usd)
        observations.append((amount, price_usd, price_source))

    snapshot_ids = [
        info.wallet_snapshot_id
        for info in balance_info.values()
        if info.wallet_snapshot_id is not None
    ]
    if snapshot_ids:
        rows = await session.execute(
            select(
                ChainSnapshot.chain,
                SnapshotBalanceSnapshot.asset_symbol,
                SnapshotBalanceSnapshot.asset_address,
                SnapshotBalanceSnapshot.asset_type,
                SnapshotBalanceSnapshot.amount,
                SnapshotBalanceSnapshot.value_usd,
                SnapshotBalanceSnapshot.price_usd,
                SnapshotBalanceSnapshot.price_source,
            )
            .join(
                SnapshotBalanceSnapshot,
                SnapshotBalanceSnapshot.chain_snapshot_id == ChainSnapshot.id,
            )
            .where(ChainSnapshot.wallet_snapshot_id.in_(snapshot_ids))
        )
        for row in rows:
            add_asset(
                key=_allocation_asset_key(
                    chain=row.chain,
                    symbol=row.asset_symbol,
                    asset_address=row.asset_address,
                    asset_type=row.asset_type,
                ),
                symbol=row.asset_symbol,
                amount=row.amount,
                value_usd=row.value_usd,
                price_usd=row.price_usd,
                price_source=row.price_source,
            )

    legacy_ids = [
        info.legacy_snapshot_id
        for info in balance_info.values()
        if info.legacy_snapshot_id is not None
    ]
    if legacy_ids:
        rows = await session.execute(
            select(
                Asset.chain,
                Asset.symbol,
                Asset.contract_address,
                BalanceSnapshot.amount,
                BalanceSnapshot.usd_value,
            )
            .join(Asset, Asset.id == BalanceSnapshot.asset_id)
            .where(BalanceSnapshot.snapshot_id.in_(legacy_ids))
        )
        for row in rows:
            price_usd = (
                row.usd_value / row.amount if row.amount != Decimal("0") else None
            )
            add_asset(
                key=_allocation_asset_key(
                    chain=row.chain,
                    symbol=row.symbol,
                    asset_address=row.contract_address,
                    asset_type="erc20" if row.contract_address else "native",
                ),
                symbol=row.symbol,
                amount=row.amount,
                value_usd=row.usd_value,
                price_usd=price_usd,
                price_source="unknown",
            )

    for wallet in wallets:
        info = balance_info[wallet.id]
        if info.wallet_snapshot_id is not None or info.legacy_snapshot_id is not None:
            continue
        for asset in info.assets:
            add_asset(
                key=_allocation_asset_key(
                    chain=asset.chain,
                    symbol=asset.symbol,
                    asset_address=None,
                    asset_type="manual",
                ),
                symbol=asset.symbol,
                amount=asset.amount,
                value_usd=asset.usd_value,
                price_usd=asset.price_usd,
                price_source="manual",
            )

    total = sum((value for _, value in asset_totals.values()), Decimal("0"))
    ordered = sorted(
        asset_totals.items(),
        key=lambda item: item[1][1],
        reverse=True,
    )
    visible = ordered[:ALLOCATION_VISIBLE_ASSETS]
    remainder = ordered[ALLOCATION_VISIBLE_ASSETS:]
    items = [
        AllocationAssetShare(
            asset_key=asset_key,
            symbol=symbol,
            usd_value=value_usd,
            share_pct=round(float(value_usd / total * 100), 2) if total else 0.0,
        )
        for asset_key, (symbol, value_usd) in visible
    ]
    other_value = sum((value for _, (_, value) in remainder), Decimal("0"))
    if other_value:
        items.append(
            AllocationAssetShare(
                asset_key="__other__",
                symbol="Other",
                usd_value=other_value,
                share_pct=round(float(other_value / total * 100), 2),
            )
        )
    return PortfolioAllocation(
        scope=scope,
        wallets_count=len(wallets),
        total_usd=total,
        items=items,
        data_quality=_allocation_quality(observations),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _portfolio_change_24h(
    session: SessionDep,
    wallets: list[Wallet],
    *,
    current_total: Decimal,
    balance_info,
    price_quality: PortfolioPriceQuality,
    health_state: str,
    freshness: str,
    chain_issues: list[PortfolioChainIssue],
) -> PortfolioValueChange24h:
    reference_at = datetime.now(timezone.utc)
    cutoff_at = reference_at - timedelta(hours=24)
    tolerance = timedelta(seconds=get_settings().portfolio_fresh_seconds)

    def result(
        status_value: str,
        reasons: list[str],
        *,
        start_usd: Decimal | None = None,
        start_times: list[datetime] | None = None,
        end_times: list[datetime] | None = None,
    ) -> PortfolioValueChange24h:
        absolute = current_total - start_usd if start_usd is not None else None
        percent = (
            round(float(absolute / start_usd * 100), 2)
            if absolute is not None and start_usd != Decimal("0")
            else None
        )
        return PortfolioValueChange24h(
            status=status_value,
            start_usd=start_usd,
            end_usd=current_total if wallets else None,
            absolute_usd=absolute,
            percent=percent,
            reference_at=reference_at,
            cutoff_at=cutoff_at,
            start_observed_from=min(start_times) if start_times else None,
            start_observed_to=max(start_times) if start_times else None,
            end_observed_from=min(end_times) if end_times else None,
            end_observed_to=max(end_times) if end_times else None,
            reason_codes=reasons,
        )

    if not wallets:
        return result("unavailable", ["no_wallets"])

    current_ids = [balance_info[wallet.id].wallet_snapshot_id for wallet in wallets]
    if any(snapshot_id is None for snapshot_id in current_ids):
        return result("unavailable", ["current_source_has_no_historical_counterpart"])

    current_rows = list(
        await session.execute(
            select(
                WalletSnapshot.id,
                WalletSnapshot.status,
                _snapshot_observed_at().label("observed_at"),
            )
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(WalletSnapshot.id.in_(current_ids))
        )
    )
    end_times = [_aware(row.observed_at) for row in current_rows]
    current_reasons = []
    if len(current_rows) != len(wallets):
        current_reasons.append("current_snapshot_missing")
    if any(row.status != "success" for row in current_rows):
        current_reasons.append("current_snapshot_partial")
    if chain_issues:
        current_reasons.append("current_chain_issues")
    if price_quality.state != "complete":
        current_reasons.append("current_price_quality")
    if health_state in {"partial", "stale"} or freshness != "fresh":
        current_reasons.append("current_data_not_fresh")
    if end_times and (
        reference_at - min(end_times) > tolerance
        or max(end_times) - min(end_times) > tolerance
    ):
        current_reasons.append("current_observation_skew")
    if current_reasons:
        return result("incomplete", current_reasons, end_times=end_times)

    observed_at = _snapshot_observed_at()
    baseline_rank = func.row_number().over(
        partition_by=WalletSnapshot.wallet_id,
        order_by=(observed_at.desc(), WalletSnapshot.id.desc()),
    )
    ranked = (
        select(
            WalletSnapshot.id.label("snapshot_id"),
            WalletSnapshot.wallet_id,
            WalletSnapshot.total_usd,
            observed_at.label("observed_at"),
            baseline_rank.label("snapshot_rank"),
        )
        .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
        .join(Wallet, Wallet.id == WalletSnapshot.wallet_id)
        .where(
            WalletSnapshot.wallet_id.in_([wallet.id for wallet in wallets]),
            WalletSnapshot.status == "success",
            observed_at <= cutoff_at,
            observed_at >= cutoff_at - tolerance,
            SnapshotRun.created_at >= Wallet.address_updated_at,
        )
        .subquery()
    )
    baseline_rows = list(
        await session.execute(
            select(
                ranked.c.snapshot_id,
                ranked.c.wallet_id,
                ranked.c.total_usd,
                ranked.c.observed_at,
            ).where(ranked.c.snapshot_rank == 1)
        )
    )
    if len(baseline_rows) != len(wallets):
        reason = (
            "wallet_address_changed"
            if any(_aware(wallet.address_updated_at) > cutoff_at for wallet in wallets)
            else "baseline_missing"
        )
        return result("unavailable", [reason], end_times=end_times)

    baseline_ids = [row.snapshot_id for row in baseline_rows]
    baseline_chain_issue = await session.scalar(
        select(func.count())
        .select_from(ChainSnapshot)
        .where(
            ChainSnapshot.wallet_snapshot_id.in_(baseline_ids),
            ChainSnapshot.status != "success",
        )
    )
    baseline_price_rows = await session.execute(
        select(
            SnapshotBalanceSnapshot.amount,
            SnapshotBalanceSnapshot.price_usd,
            SnapshotBalanceSnapshot.price_source,
        )
        .join(
            ChainSnapshot,
            ChainSnapshot.id == SnapshotBalanceSnapshot.chain_snapshot_id,
        )
        .where(ChainSnapshot.wallet_snapshot_id.in_(baseline_ids))
    )
    baseline_quality = _portfolio_price_quality(
        [(row.amount, row.price_usd, row.price_source) for row in baseline_price_rows]
    )
    start_times = [_aware(row.observed_at) for row in baseline_rows]
    baseline_reasons = []
    if baseline_chain_issue:
        baseline_reasons.append("baseline_chain_issues")
    if baseline_quality.state != "complete":
        baseline_reasons.append("baseline_price_quality")
    if max(start_times) - min(start_times) > tolerance:
        baseline_reasons.append("baseline_observation_skew")
    if baseline_reasons:
        return result(
            "incomplete",
            baseline_reasons,
            start_times=start_times,
            end_times=end_times,
        )

    start_total = sum(
        (row.total_usd for row in baseline_rows),
        Decimal("0"),
    )
    if start_total == Decimal("0"):
        return result(
            "unavailable",
            ["baseline_zero"],
            start_usd=start_total,
            start_times=start_times,
            end_times=end_times,
        )
    return result(
        "complete",
        [],
        start_usd=start_total,
        start_times=start_times,
        end_times=end_times,
    )


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
    observed_at = _snapshot_observed_at()
    rows = list(
        await session.execute(
            select(
                WalletSnapshot.wallet_id,
                observed_at.label("snapshot_at"),
                WalletSnapshot.total_usd,
            )
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(
                WalletSnapshot.wallet_id.in_(wallet_ids),
                WalletSnapshot.status.in_(HISTORY_READ_STATUSES),
                observed_at >= since,
            )
            .order_by(observed_at, WalletSnapshot.id)
        )
    )

    first_new_rows = await session.execute(
        select(
            WalletSnapshot.wallet_id,
            func.min(observed_at).label("first_snapshot_at"),
        )
        .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
        .where(
            WalletSnapshot.wallet_id.in_(wallet_ids),
            WalletSnapshot.status.in_(HISTORY_READ_STATUSES),
        )
        .group_by(WalletSnapshot.wallet_id)
    )
    first_new_by_wallet = {
        row.wallet_id: row.first_snapshot_at for row in first_new_rows
    }
    legacy_rows = await session.execute(
        select(Snapshot.wallet_id, Snapshot.snapshot_at, Snapshot.total_usd)
        .where(
            Snapshot.wallet_id.in_(wallet_ids),
            Snapshot.snapshot_at >= since,
        )
        .order_by(Snapshot.snapshot_at, Snapshot.id)
    )
    rows.extend(
        row
        for row in legacy_rows
        if row.wallet_id not in first_new_by_wallet
        or row.snapshot_at < first_new_by_wallet[row.wallet_id]
    )

    rows.sort(key=lambda row: (row.snapshot_at, row.wallet_id))
    if wallet_id is not None:
        points = [
            PortfolioPoint(snapshot_at=row.snapshot_at, total_usd=row.total_usd)
            for row in rows
        ]
    else:
        latest_before_rank = func.row_number().over(
            partition_by=WalletSnapshot.wallet_id,
            order_by=(observed_at.desc(), WalletSnapshot.id.desc()),
        )
        latest_before = (
            select(
                WalletSnapshot.wallet_id,
                WalletSnapshot.total_usd,
                observed_at.label("snapshot_at"),
                latest_before_rank.label("snapshot_rank"),
            )
            .join(SnapshotRun, SnapshotRun.id == WalletSnapshot.snapshot_run_id)
            .where(
                WalletSnapshot.wallet_id.in_(wallet_ids),
                WalletSnapshot.status.in_(HISTORY_READ_STATUSES),
                observed_at < since,
            )
            .subquery()
        )
        seed_by_wallet = {
            row.wallet_id: (row.snapshot_at, row.total_usd)
            for row in await session.execute(
                select(
                    latest_before.c.wallet_id,
                    latest_before.c.snapshot_at,
                    latest_before.c.total_usd,
                ).where(latest_before.c.snapshot_rank == 1)
            )
        }
        legacy_before_rows = await session.execute(
            select(Snapshot.wallet_id, Snapshot.snapshot_at, Snapshot.total_usd)
            .where(
                Snapshot.wallet_id.in_(wallet_ids),
                Snapshot.snapshot_at < since,
            )
            .order_by(Snapshot.snapshot_at.desc(), Snapshot.id.desc())
        )
        legacy_seen: set[int] = set()
        for row in legacy_before_rows:
            if row.wallet_id in legacy_seen:
                continue
            first_new = first_new_by_wallet.get(row.wallet_id)
            if first_new is not None and row.snapshot_at >= first_new:
                continue
            legacy_seen.add(row.wallet_id)
            current_seed = seed_by_wallet.get(row.wallet_id)
            if current_seed is None or row.snapshot_at > current_seed[0]:
                seed_by_wallet[row.wallet_id] = (
                    row.snapshot_at,
                    row.total_usd,
                )
        balance_by_wallet = {
            seed_wallet_id: total_usd
            for seed_wallet_id, (_, total_usd) in seed_by_wallet.items()
        }

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


@router.get("/allocation", response_model=PortfolioAllocation)
async def portfolio_allocation(
    current_user: CurrentUser,
    session: SessionDep,
    mode: str = Query(default="all", pattern="^(all|selection)$"),
    group_id: list[int] | None = Query(default=None),
    include_ungrouped: bool = Query(default=False),
) -> PortfolioAllocation:
    requested_group_ids = list(dict.fromkeys(group_id or []))
    if mode == "all":
        if requested_group_ids or include_ungrouped:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Group filters require mode=selection",
            )
        scope: PortfolioAllScope | PortfolioSelectionScope = PortfolioAllScope(
            mode="all"
        )
        wallets = await _active_canonical_wallets(
            session,
            user_id=current_user.id,
        )
    else:
        if not requested_group_ids and not include_ungrouped:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Select at least one group or include ungrouped wallets",
            )
        if requested_group_ids:
            owned_ids = set(
                await session.scalars(
                    select(WalletGroup.id).where(
                        WalletGroup.user_id == current_user.id,
                        WalletGroup.id.in_(requested_group_ids),
                    )
                )
            )
            if owned_ids != set(requested_group_ids):
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    "Wallet group not found",
                )
        scope = PortfolioSelectionScope(
            mode="selection",
            group_ids=requested_group_ids,
            include_ungrouped=include_ungrouped,
        )
        wallets = await _active_canonical_wallets(
            session,
            user_id=current_user.id,
            group_ids=requested_group_ids,
            include_ungrouped=include_ungrouped,
        )
    return await _allocation_for_wallets(session, wallets, scope=scope)


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    current_user: CurrentUser,
    session: SessionDep,
) -> PortfolioSummary:
    wallets = await _active_canonical_wallets(
        session,
        user_id=current_user.id,
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
    # The conservative portfolio timestamp is the oldest automated source
    # contributing to the total. A newest-wallet timestamp would hide stale
    # wallets behind one recently refreshed wallet.
    as_of = min(snapshot_dates) if snapshot_dates else None

    snapshot_wallets = sum(
        balance_info[wallet.id].balance_source == "latest_snapshot"
        for wallet in wallets
    )
    manual_wallets = sum(
        balance_info[wallet.id].balance_source == "manual" for wallet in wallets
    )
    missing_wallets = sum(
        balance_info[wallet.id].balance_source == "none" for wallet in wallets
    )
    wallets_covered = snapshot_wallets + manual_wallets

    refresh_in_progress = bool(
        await session.scalar(
            select(func.count())
            .select_from(SnapshotRun)
            .where(
                SnapshotRun.user_id == current_user.id,
                SnapshotRun.status.in_(ACTIVE_SNAPSHOT_STATUSES),
            )
        )
    )

    latest_snapshot_ids = [
        balance_info[wallet.id].wallet_snapshot_id
        for wallet in wallets
        if balance_info[wallet.id].wallet_snapshot_id is not None
    ]
    issue_rows = []
    if latest_snapshot_ids:
        issue_rows = list(
            await session.execute(
                select(
                    ChainSnapshot.chain,
                    ChainSnapshot.status,
                    ChainSnapshot.error_type,
                    ChainSnapshot.wallet_snapshot_id,
                    WalletSnapshot.snapshot_run_id,
                )
                .join(
                    WalletSnapshot,
                    WalletSnapshot.id == ChainSnapshot.wallet_snapshot_id,
                )
                .where(
                    ChainSnapshot.wallet_snapshot_id.in_(latest_snapshot_ids),
                    ChainSnapshot.status != "success",
                )
                .order_by(ChainSnapshot.chain, ChainSnapshot.wallet_snapshot_id)
            )
        )
    issue_by_chain: dict[str, dict[str, object]] = {}
    retryable_run_ids: set[int] = set()
    for row in issue_rows:
        issue = issue_by_chain.setdefault(
            row.chain,
            {
                "statuses": set(),
                "error_types": set(),
                "wallet_ids": set(),
            },
        )
        issue["statuses"].add(row.status)
        if row.error_type:
            issue["error_types"].add(row.error_type)
        issue["wallet_ids"].add(row.wallet_snapshot_id)
        if row.status == "failed":
            retryable_run_ids.add(row.snapshot_run_id)
    chain_issues = []
    for chain, issue in sorted(issue_by_chain.items()):
        statuses = issue["statuses"]
        error_types = issue["error_types"]
        chain_issues.append(
            PortfolioChainIssue(
                chain=chain,
                status="failed" if "failed" in statuses else sorted(statuses)[0],
                error_type=(
                    next(iter(error_types))
                    if len(error_types) == 1
                    else ("multiple_errors" if error_types else None)
                ),
                wallets_count=len(issue["wallet_ids"]),
            )
        )

    price_observations: list[tuple[Decimal, Decimal | None, str | None]] = []
    if latest_snapshot_ids:
        price_rows = await session.execute(
            select(
                SnapshotBalanceSnapshot.amount,
                SnapshotBalanceSnapshot.price_usd,
                SnapshotBalanceSnapshot.price_source,
            )
            .join(
                ChainSnapshot,
                ChainSnapshot.id == SnapshotBalanceSnapshot.chain_snapshot_id,
            )
            .where(ChainSnapshot.wallet_snapshot_id.in_(latest_snapshot_ids))
        )
        price_observations.extend(
            (row.amount, row.price_usd, row.price_source) for row in price_rows
        )

    for wallet in wallets:
        info = balance_info[wallet.id]
        if info.wallet_snapshot_id is not None:
            continue
        source = "manual" if info.balance_source == "manual" else None
        price_observations.extend(
            (asset.amount, asset.price_usd, source) for asset in info.assets
        )
    price_quality = _portfolio_price_quality(price_observations)

    settings = get_settings()
    freshness = _portfolio_freshness(
        as_of,
        fresh_seconds=settings.portfolio_fresh_seconds,
        stale_seconds=settings.portfolio_stale_seconds,
    )
    if chain_issues or price_quality.state in {"estimated", "incomplete"}:
        health_state = "partial"
    elif refresh_in_progress:
        health_state = "updating"
    elif missing_wallets:
        health_state = "partial"
    elif freshness == "stale":
        health_state = "stale"
    else:
        health_state = "fresh"

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

    change_24h = await _portfolio_change_24h(
        session,
        wallets,
        current_total=total,
        balance_info=balance_info,
        price_quality=price_quality,
        health_state=health_state,
        freshness=freshness,
        chain_issues=chain_issues,
    )

    return PortfolioSummary(
        total_usd=total,
        wallets_count=wallets_count,
        active_wallets_count=active_wallets_count,
        last_snapshot_at=last_snapshot_at,
        top_assets=top_assets,
        data_health=PortfolioDataHealth(
            state=health_state,
            freshness=freshness,
            as_of=as_of,
            wallets_covered=wallets_covered,
            wallets_total=active_wallets_count,
            snapshot_wallets=snapshot_wallets,
            manual_wallets=manual_wallets,
            missing_wallets=missing_wallets,
            refresh_in_progress=refresh_in_progress,
            retryable_job_id=(
                next(iter(retryable_run_ids)) if len(retryable_run_ids) == 1 else None
            ),
            chain_issues=chain_issues,
            price_quality=price_quality,
        ),
        change_24h=change_24h,
    )
