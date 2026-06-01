from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SnapshotCreate(BaseModel):
    wallet_id: int | None = None  # None => снять снапшот всех кошельков пользователя


class BalanceRead(BaseModel):
    symbol: str
    amount: Decimal
    usd_value: Decimal


class SnapshotRead(BaseModel):
    id: int
    wallet_id: int
    snapshot_at: datetime
    total_usd: Decimal
    balances: list[BalanceRead] = []
