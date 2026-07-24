"""enforce active EVM wallet uniqueness

Revision ID: g7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-24 14:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7a8b9c0d1e2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshot-service owns its four read-model tables and its separate Alembic
    # version chain. This API revision must never create, alter, or drop them.
    # Keep the oldest active wallet as canonical before enforcing the API-owned
    # invariant for future writes.
    op.execute(sa.text("""
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY user_id, lower(btrim(address))
                        ORDER BY id
                    ) AS duplicate_rank
                FROM wallets
                WHERE wallet_type = 'evm'
                  AND is_active IS TRUE
                  AND address IS NOT NULL
            )
            UPDATE wallets
            SET is_active = false
            WHERE id IN (
                SELECT id FROM ranked WHERE duplicate_rank > 1
            )
            """))
    op.create_index(
        "uq_wallets_active_evm_address",
        "wallets",
        ["user_id", sa.text("lower(btrim(address))")],
        unique=True,
        postgresql_where=sa.text(
            "wallet_type = 'evm' AND is_active IS TRUE AND address IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_wallets_active_evm_address", table_name="wallets")
