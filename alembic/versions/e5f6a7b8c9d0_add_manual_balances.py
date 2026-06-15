"""manual_balances table and nullable assets.contract_address

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-15 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "assets",
        "contract_address",
        existing_type=sa.String(length=128),
        nullable=True,
    )
    op.create_index(
        "uq_assets_chain_symbol_manual",
        "assets",
        ["chain", "symbol"],
        unique=True,
        postgresql_where=sa.text("contract_address IS NULL"),
    )
    op.create_table(
        "manual_balances",
        sa.Column("wallet_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("price_usd", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("wallet_id", "asset_id"),
    )


def downgrade() -> None:
    op.drop_table("manual_balances")
    op.drop_index("uq_assets_chain_symbol_manual", table_name="assets")
    op.execute(
        sa.text(
            "UPDATE assets SET contract_address = '' WHERE contract_address IS NULL"
        )
    )
    op.alter_column(
        "assets",
        "contract_address",
        existing_type=sa.String(length=128),
        nullable=False,
    )
