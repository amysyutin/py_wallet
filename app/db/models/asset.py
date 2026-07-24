from __future__ import annotations

from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("chain", "contract_address", name="uq_assets_chain_contract"),
        Index(
            "uq_assets_chain_symbol_manual",
            "chain",
            "symbol",
            unique=True,
            postgresql_where=text("contract_address IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    contract_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chain: Mapped[str] = mapped_column(String(32))
    decimals: Mapped[int] = mapped_column(Integer, default=18)
