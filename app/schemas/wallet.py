from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import CHAIN_RPC

SUPPORTED_CHAINS = set(CHAIN_RPC) | {"binance"}


class WalletCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    wallet_type: Literal["evm"] = "evm"
    address: str = Field(min_length=1, max_length=128)
    chain_type: str
    group_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("chain_type")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        if v not in SUPPORTED_CHAINS:
            raise ValueError(f"chain_type must be one of {sorted(SUPPORTED_CHAINS)}")
        return v


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
    address: str
    chain_type: str
    wallet_type: str
    group_id: int | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
