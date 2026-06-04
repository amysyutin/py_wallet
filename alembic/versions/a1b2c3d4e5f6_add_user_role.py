"""add user role column

Revision ID: a1b2c3d4e5f6
Revises: dd0ebf5031f5
Create Date: 2026-06-04 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "dd0ebf5031f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role_enum = sa.Enum(
    "user",
    "admin",
    name="user_role",
    native_enum=False,
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="user",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
