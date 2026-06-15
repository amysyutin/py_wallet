from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import CHAIN_RPC

SUPPORTED_CHAINS = set(CHAIN_RPC) | {"binance"}


class WalletCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    wallet_type: Literal["evm", "manual"] = "evm"
    address: str | None = Field(default=None, max_length=128)
    chain_type: str
    group_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_wallet_type_rules(self) -> "WalletCreate":
        if self.wallet_type == "evm":
            if not self.address or not self.address.strip():
                raise ValueError("address is required for EVM wallets")
            if self.chain_type == "manual":
                raise ValueError("chain_type cannot be 'manual' for EVM wallets")
            if self.chain_type not in SUPPORTED_CHAINS:
                raise ValueError(
                    f"chain_type must be one of {sorted(SUPPORTED_CHAINS)}"
                )
        elif self.wallet_type == "manual":
            if self.chain_type != "manual":
                raise ValueError("chain_type must be 'manual' for manual wallets")
        return self


class WalletUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=100)
    group_id: int | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    address: str | None
    chain_type: str
    wallet_type: str
    group_id: int | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
