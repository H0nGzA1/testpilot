"""account health: credential healthy / last_error / last_checked_at

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-13 05:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as b:
        b.add_column(sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("last_error", sa.String(length=500), nullable=True))
        b.add_column(sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as b:
        b.drop_column("last_checked_at")
        b.drop_column("last_error")
        b.drop_column("healthy")
