from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class PortfolioPoint(BaseModel):
    snapshot_at: datetime
    total_usd: Decimal


class PortfolioHistory(BaseModel):
    wallet_id: int | None = None
    group_id: int | None = None
    days: int
    points: list[PortfolioPoint]


class AssetShare(BaseModel):
    symbol: str
    usd_value: Decimal
    share_pct: float


class PortfolioChainIssue(BaseModel):
    chain: str
    status: str
    error_type: str | None = None
    wallets_count: int


class PortfolioPriceQuality(BaseModel):
    state: Literal["complete", "estimated", "incomplete", "unknown"]
    sources: list[Literal["coingecko", "manual", "static_dev", "unknown"]]
    assets_priced: int
    assets_total: int


class PortfolioDataHealth(BaseModel):
    state: Literal["fresh", "updating", "partial", "stale"]
    freshness: Literal["fresh", "aging", "stale", "unknown"]
    as_of: datetime | None = None
    wallets_covered: int
    wallets_total: int
    snapshot_wallets: int
    manual_wallets: int
    missing_wallets: int
    refresh_in_progress: bool
    chain_issues: list[PortfolioChainIssue]
    price_quality: PortfolioPriceQuality


class PortfolioSummary(BaseModel):
    total_usd: Decimal
    wallets_count: int
    active_wallets_count: int
    last_snapshot_at: datetime | None = None
    top_assets: list[AssetShare]
    data_health: PortfolioDataHealth
