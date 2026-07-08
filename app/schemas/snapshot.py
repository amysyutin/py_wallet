from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator


class SnapshotCreate(BaseModel):
    scope_type: Literal["all", "group", "wallet"] = "all"
    wallet_id: int | None = None
    group_id: int | None = None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "SnapshotCreate":
        # Backward compat: {wallet_id: N} without scope_type => wallet
        if (
            self.scope_type == "all"
            and self.wallet_id is not None
            and self.group_id is None
        ):
            self.scope_type = "wallet"
        elif (
            self.scope_type == "all"
            and self.group_id is not None
            and self.wallet_id is None
        ):
            self.scope_type = "group"

        if self.scope_type == "wallet":
            if self.wallet_id is None:
                raise ValueError("wallet_id is required when scope_type is 'wallet'")
            if self.group_id is not None:
                raise ValueError("group_id must be null when scope_type is 'wallet'")
        elif self.scope_type == "group":
            if self.group_id is None:
                raise ValueError("group_id is required when scope_type is 'group'")
            if self.wallet_id is not None:
                raise ValueError("wallet_id must be null when scope_type is 'group'")
        elif self.scope_type == "all":
            if self.wallet_id is not None or self.group_id is not None:
                raise ValueError(
                    "wallet_id and group_id must be null when scope_type is 'all'"
                )
        return self


class SnapshotJobRead(BaseModel):
    job_id: int
    status: str


class SnapshotJobDetail(BaseModel):
    job_id: int
    status: str
    scope_type: str
    wallet_id: int | None
    group_id: int | None = None
    trigger_type: str
    created_at: datetime
    finished_at: datetime | None
    error_message: str | None


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
