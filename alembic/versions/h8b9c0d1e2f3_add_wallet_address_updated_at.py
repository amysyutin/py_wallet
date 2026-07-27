"""track the wallet address revision used by snapshots

Revision ID: h8b9c0d1e2f3
Revises: g7a8b9c0d1e2
Create Date: 2026-07-27 23:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8b9c0d1e2f3"
down_revision: Union[str, None] = "g7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column("address_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing snapshots do not persist their captured address, so invalidate
    # them conservatively instead of risking balances from an old address.
    op.execute(sa.text("UPDATE wallets SET address_updated_at = now()"))
    op.alter_column(
        "wallets",
        "address_updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.drop_column("wallets", "address_updated_at")
