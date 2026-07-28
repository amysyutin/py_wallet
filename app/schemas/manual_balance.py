from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class ManualBalanceItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    chain: str = Field(default="manual", min_length=1, max_length=32)
    amount: Decimal = Field(ge=0)
    price_usd: Decimal | None = Field(default=None, ge=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be blank")
        return normalized

    @field_validator("chain", mode="before")
    @classmethod
    def normalize_chain(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().lower() or "manual"


class ManualBalancesPut(BaseModel):
    balances: list[ManualBalanceItemCreate]

    @model_validator(mode="after")
    def reject_duplicate_assets(self) -> "ManualBalancesPut":
        seen: set[tuple[str, str]] = set()
        for item in self.balances:
            key = (item.chain, item.symbol)
            if key in seen:
                raise ValueError(
                    f"duplicate manual asset after normalization: {item.chain}/{item.symbol}"
                )
            seen.add(key)
        return self


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
