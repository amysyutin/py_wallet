from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("chain", "contract_address", name="uq_assets_chain_contract"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    contract_address: Mapped[str] = mapped_column(String(128))
    chain: Mapped[str] = mapped_column(String(32))
    decimals: Mapped[int] = mapped_column(Integer, default=18)
