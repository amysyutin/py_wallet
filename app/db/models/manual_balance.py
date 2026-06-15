from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.asset import Asset
    from app.db.models.wallet import Wallet


class ManualBalance(Base):
    __tablename__ = "manual_balances"

    wallet_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("wallets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    wallet: Mapped[Wallet] = relationship(back_populates="manual_balances")
    asset: Mapped[Asset] = relationship()
