from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.asset import Asset
    from app.db.models.snapshot import Snapshot


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (Index("ix_balance_snapshots_asset", "asset_id"),)

    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assets.id", ondelete="RESTRICT"), primary_key=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    usd_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)

    snapshot: Mapped[Snapshot] = relationship(back_populates="balances")
    asset: Mapped[Asset] = relationship()
