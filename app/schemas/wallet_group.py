from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WalletGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class WalletGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None


class WalletGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    sort_order: int
    wallets_count: int = 0
    created_at: datetime
    updated_at: datetime
