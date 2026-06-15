from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ManualBalanceItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    chain: str = "manual"
    amount: Decimal = Field(ge=0)
    price_usd: Decimal | None = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("chain")
    @classmethod
    def normalize_chain(cls, v: str) -> str:
        return v.strip().lower() or "manual"


class ManualBalancesPut(BaseModel):
    balances: list[ManualBalanceItemCreate]


class ManualBalanceItemRead(BaseModel):
    asset_id: int
    symbol: str
    chain: str
    amount: Decimal
    price_usd: Decimal | None
    value_usd: Decimal


class ManualBalancesRead(BaseModel):
    wallet_id: int
    wallet_label: str
    wallet_type: str
    balances: list[ManualBalanceItemRead]
    total_usd: Decimal
