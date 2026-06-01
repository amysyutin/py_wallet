from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.asset import Asset
    from app.db.models.wallet import Wallet


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "wallet_id", "tx_hash", "asset_id", name="uq_tx_wallet_hash_asset"
        ),
        CheckConstraint("direction IN ('in','out')", name="ck_tx_direction"),
        Index("ix_transactions_wallet", "wallet_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wallets.id", ondelete="CASCADE")
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assets.id", ondelete="RESTRICT")
    )
    tx_hash: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    usd_price_at_tx: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    tx_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")
    asset: Mapped[Asset] = relationship()
