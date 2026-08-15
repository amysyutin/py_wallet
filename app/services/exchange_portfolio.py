from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.connectors.price.coingecko import get_coin_price_usd_cached
from app.core.config import Settings

ExchangePortfolioStatus = Literal[
    "not_configured",
    "success",
    "not_found",
    "timeout",
    "unavailable",
    "invalid_response",
]

EXCHANGE_COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
}


class _ExchangeBalancePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9]+$")
    free: Decimal = Field(ge=0)
    locked: Decimal = Field(ge=0)
    total: Decimal = Field(gt=0)

    @field_validator("total")
    @classmethod
    def total_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("total must be finite")
        return value


class _ExchangeSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    exchange: Literal["binance"]
    status: Literal["success"]
    created_at: datetime
    completed_at: datetime
    balances: list[_ExchangeBalancePayload] = Field(max_length=500)


@dataclass(frozen=True)
class ExchangeAssetPosition:
    symbol: str
    amount: Decimal
    price_usd: Decimal | None
    usd_value: Decimal


@dataclass(frozen=True)
class ExchangePortfolioSnapshot:
    provider: Literal["binance"]
    status: ExchangePortfolioStatus
    as_of: datetime | None = None
    assets: tuple[ExchangeAssetPosition, ...] = ()
    error_type: str | None = None

    @property
    def configured(self) -> bool:
        return self.status != "not_configured"

    @property
    def total_usd(self) -> Decimal:
        return sum((asset.usd_value for asset in self.assets), Decimal("0"))


def _failed(status: ExchangePortfolioStatus) -> ExchangePortfolioSnapshot:
    return ExchangePortfolioSnapshot(
        provider="binance",
        status=status,
        error_type=None if status == "not_configured" else status,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def fetch_exchange_portfolio(
    settings: Settings,
    *,
    user_id: int,
) -> ExchangePortfolioSnapshot:
    """Load and value a user's latest CEX snapshot without exposing provider details."""
    if not settings.exchange_internal_api_token:
        return _failed("not_configured")

    try:
        response = requests.get(
            f"{settings.exchange_service_url.rstrip('/')}/internal/exchange-snapshots/latest",
            params={"user_id": user_id},
            headers={"X-Internal-Token": settings.exchange_internal_api_token},
            timeout=settings.exchange_service_timeout_seconds,
        )
    except requests.Timeout:
        return _failed("timeout")
    except requests.RequestException:
        return _failed("unavailable")

    if response.status_code == 404:
        return _failed("not_found")
    if response.status_code != 200:
        return _failed("unavailable")

    try:
        payload = _ExchangeSnapshotPayload.model_validate(response.json())
    except (ValueError, ValidationError):
        return _failed("invalid_response")
    if payload.user_id != user_id:
        return _failed("invalid_response")
    completed_at = _aware(payload.completed_at)
    if completed_at < _aware(payload.created_at):
        return _failed("invalid_response")
    if len({balance.asset for balance in payload.balances}) != len(payload.balances):
        return _failed("invalid_response")
    if any(
        balance.total != balance.free + balance.locked for balance in payload.balances
    ):
        return _failed("invalid_response")

    assets = []
    for balance in payload.balances:
        price_usd = None
        coin_id = EXCHANGE_COIN_IDS.get(balance.asset)
        if coin_id:
            try:
                price_usd = Decimal(str(get_coin_price_usd_cached(coin_id)))
                if not price_usd.is_finite() or price_usd <= 0:
                    price_usd = None
            except Exception:
                price_usd = None
        assets.append(
            ExchangeAssetPosition(
                symbol=balance.asset,
                amount=balance.total,
                price_usd=price_usd,
                usd_value=(
                    balance.total * price_usd if price_usd is not None else Decimal("0")
                ),
            )
        )

    return ExchangePortfolioSnapshot(
        provider=payload.exchange,
        status="success",
        as_of=completed_at,
        assets=tuple(assets),
    )
