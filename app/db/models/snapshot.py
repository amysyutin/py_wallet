from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.balance_snapshot import BalanceSnapshot
    from app.db.models.wallet import Wallet


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_wallet_at", "wallet_id", "snapshot_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wallets.id", ondelete="CASCADE")
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    total_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)

    wallet: Mapped[Wallet] = relationship(back_populates="snapshots")
    balances: Mapped[list[BalanceSnapshot]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
