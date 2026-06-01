from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import CHAIN_RPC

SUPPORTED_CHAINS = set(CHAIN_RPC) | {"binance"}


class WalletCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=128)
    chain_type: str

    @field_validator("chain_type")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        if v not in SUPPORTED_CHAINS:
            raise ValueError(f"chain_type must be one of {sorted(SUPPORTED_CHAINS)}")
        return v


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    address: str
    chain_type: str
    created_at: datetime