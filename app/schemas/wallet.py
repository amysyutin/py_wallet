from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import CHAIN_RPC

SUPPORTED_CHAINS = set(CHAIN_RPC)


def validate_wallet_network_state(
    wallet_type: str, chain_type: str, address: str | None
) -> None:
    if wallet_type == "evm":
        if not address or not address.strip():
            raise ValueError("address is required for EVM wallets")
        if chain_type == "manual":
            raise ValueError("chain_type cannot be 'manual' for EVM wallets")
        if chain_type not in SUPPORTED_CHAINS:
            raise ValueError(f"chain_type must be one of {sorted(SUPPORTED_CHAINS)}")
    elif wallet_type == "manual":
        if chain_type != "manual":
            raise ValueError("chain_type must be 'manual' for manual wallets")
        if address is not None:
            raise ValueError("manual wallets cannot have an address")


class WalletCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    wallet_type: Literal["evm", "manual"] = "evm"
    address: str | None = Field(default=None, max_length=128)
    chain_type: str
    group_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_wallet_type_rules(self) -> "WalletCreate":
        validate_wallet_network_state(self.wallet_type, self.chain_type, self.address)
        return self


class WalletUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, max_length=128)
    chain_type: str | None = None
    group_id: int | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "WalletUpdate":
        for field_name in ("label", "chain_type", "is_active"):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")
        return self


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


class WalletTopAsset(BaseModel):
    symbol: str
    amount: Decimal
    usd_value: Decimal


class WalletAssetDetail(BaseModel):
    symbol: str
    chain: str
    amount: Decimal
    usd_value: Decimal
    price_usd: Decimal | None = None


class WalletSummaryRead(BaseModel):
    id: int
    label: str
    wallet_type: str
    chain_type: str
    address: str | None
    group_id: int | None
    group_name: str | None = None
    is_active: bool
    balance_usd: Decimal
    balance_source: Literal["latest_snapshot", "manual", "none"]
    last_snapshot_at: datetime | None
    balances_count: int
    top_assets: list[WalletTopAsset]
    created_at: datetime
    updated_at: datetime


class WalletDetailSummary(BaseModel):
    wallet: WalletRead
    balance_usd: Decimal
    last_snapshot_at: datetime | None
    assets: list[WalletAssetDetail]


class WalletSnapshotRead(BaseModel):
    id: int
    snapshot_run_id: int
    status: str
    total_usd: Decimal
    snapshot_at: datetime
