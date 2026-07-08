from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SnapshotRun(Base):
    __tablename__ = "snapshot_runs"
    __table_args__ = (
        Index("ix_snapshot_runs_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    wallet_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(1000))

    wallet_snapshots: Mapped[list[WalletSnapshot]] = relationship(
        back_populates="snapshot_run"
    )


class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"
    __table_args__ = (
        Index("ix_wallet_snapshots_run_id", "snapshot_run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("snapshot_runs.id", ondelete="CASCADE")
    )
    wallet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wallets.id", ondelete="CASCADE"), index=True
    )
    wallet_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    total_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)

    snapshot_run: Mapped[SnapshotRun] = relationship(
        back_populates="wallet_snapshots"
    )
    chain_snapshots: Mapped[list[ChainSnapshot]] = relationship(
        back_populates="wallet_snapshot"
    )


class ChainSnapshot(Base):
    __tablename__ = "chain_snapshots"
    __table_args__ = (
        Index("ix_chain_snapshots_wallet_snapshot_id", "wallet_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wallet_snapshots.id", ondelete="CASCADE")
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    total_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))

    wallet_snapshot: Mapped[WalletSnapshot] = relationship(
        back_populates="chain_snapshots"
    )
    balance_snapshots: Mapped[list[SnapshotBalanceSnapshot]] = relationship(
        back_populates="chain_snapshot"
    )


class SnapshotBalanceSnapshot(Base):
    __tablename__ = "snapshot_balance_snapshots"
    __table_args__ = (
        Index("ix_snapshot_balance_snapshots_chain_snapshot_id", "chain_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chain_snapshots.id", ondelete="CASCADE")
    )
    asset_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    value_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    price_source: Mapped[str | None] = mapped_column(String(64))

    chain_snapshot: Mapped[ChainSnapshot] = relationship(
        back_populates="balance_snapshots"
    )
