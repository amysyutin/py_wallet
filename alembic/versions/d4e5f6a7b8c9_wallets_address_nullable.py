"""wallets address nullable for manual wallets

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-15 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "wallets",
        "address",
        existing_type=sa.String(length=128),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE wallets SET address = '' WHERE address IS NULL"))
    op.alter_column(
        "wallets",
        "address",
        existing_type=sa.String(length=128),
        nullable=False,
    )
