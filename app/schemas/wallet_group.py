from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WalletGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class WalletGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "WalletGroupUpdate":
        for field_name in ("name", "sort_order"):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")
        return self


class WalletGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    sort_order: int
    wallets_count: int = 0
    created_at: datetime
    updated_at: datetime
