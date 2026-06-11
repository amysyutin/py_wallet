"""extend wallets for mvp sprint 1

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-11 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wallets", sa.Column("group_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "wallets",
        sa.Column("wallet_type", sa.String(length=32), nullable=False, server_default="evm"),
    )
    op.add_column(
        "wallets",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("wallets", sa.Column("notes", sa.String(length=500), nullable=True))
    op.add_column(
        "wallets",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Attach existing wallets to Default group of their user.
    op.execute(
        sa.text(
            """
            UPDATE wallets w
            SET group_id = wg.id
            FROM wallet_groups wg
            WHERE wg.user_id = w.user_id
              AND wg.name = 'Default'
            """
        )
    )

    op.create_foreign_key(
        "fk_wallets_group_id",
        "wallets",
        "wallet_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_wallets_group_id"), "wallets", ["group_id"], unique=False)
    op.create_index(
        "ix_wallets_user_id_is_active", "wallets", ["user_id", "is_active"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_wallets_user_id_is_active", table_name="wallets")
    op.drop_index(op.f("ix_wallets_group_id"), table_name="wallets")
    op.drop_constraint("fk_wallets_group_id", "wallets", type_="foreignkey")
    op.drop_column("wallets", "updated_at")
    op.drop_column("wallets", "notes")
    op.drop_column("wallets", "is_active")
    op.drop_column("wallets", "wallet_type")
    op.drop_column("wallets", "group_id")
