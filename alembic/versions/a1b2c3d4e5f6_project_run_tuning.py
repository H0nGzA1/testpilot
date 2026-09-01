"""project run tuning columns

Revision ID: a1b2c3d4e5f6
Revises: 9f3a1c7d2e40
Create Date: 2026-08-11 17:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9f3a1c7d2e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project", schema=None) as b:
        b.add_column(sa.Column("case_timeout_s", sa.Integer(), nullable=True))
        b.add_column(sa.Column("case_max_steps", sa.Integer(), nullable=True))
        b.add_column(sa.Column("run_concurrency", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("project", schema=None) as b:
        b.drop_column("run_concurrency")
        b.drop_column("case_max_steps")
        b.drop_column("case_timeout_s")
