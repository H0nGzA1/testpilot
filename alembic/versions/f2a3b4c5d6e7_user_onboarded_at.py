"""app_user.onboarded_at (guided first-run flow)

NULL means "hasn't been through the guided flow", so it opens on next sign-in.
Existing rows stay NULL on purpose — everyone gets it once.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-26 04:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_column("onboarded_at")
