"""add Telegram Mini App identities and daily balance delivery

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-19 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users", "email", existing_type=sa.String(length=320), nullable=True
    )
    op.alter_column(
        "users", "auth_hash", existing_type=sa.String(length=255), nullable=True
    )
    op.create_table(
        "telegram_accounts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column(
            "allows_write_to_pm",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "last_authenticated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "telegram_notification_settings",
        sa.Column("telegram_account_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "timezone", sa.String(length=64), server_default="UTC", nullable=False
        ),
        sa.Column("daily_at", sa.Time(), server_default="09:00:00", nullable=False),
        sa.Column("language", sa.String(length=2), server_default="en", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("language IN ('ru', 'en')", name="ck_telegram_language"),
        sa.ForeignKeyConstraint(
            ["telegram_account_id"], ["telegram_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("telegram_account_id"),
    )
    op.create_table(
        "telegram_digest_deliveries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_account_id", sa.BigInteger(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_usd", sa.String(length=64), nullable=False),
        sa.Column("error", sa.String(length=250), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="ck_telegram_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_account_id"], ["telegram_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "telegram_account_id", "local_date", name="uq_telegram_digest_local_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("telegram_digest_deliveries")
    op.drop_table("telegram_notification_settings")
    op.drop_table("telegram_accounts")
    op.execute(sa.text("DELETE FROM users WHERE email IS NULL OR auth_hash IS NULL"))
    op.alter_column(
        "users", "auth_hash", existing_type=sa.String(length=255), nullable=False
    )
    op.alter_column(
        "users", "email", existing_type=sa.String(length=320), nullable=False
    )
