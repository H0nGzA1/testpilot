"""run_result diagnostics column

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-12 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("run_result", schema=None) as b:
        b.add_column(sa.Column("diagnostics", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("run_result", schema=None) as b:
        b.drop_column("diagnostics")
