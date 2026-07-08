from datetime import datetime
from decimal import Decimal

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


class PortfolioSummary(BaseModel):
    total_usd: Decimal
    wallets_count: int
    active_wallets_count: int
    last_snapshot_at: datetime | None = None
    top_assets: list[AssetShare]
