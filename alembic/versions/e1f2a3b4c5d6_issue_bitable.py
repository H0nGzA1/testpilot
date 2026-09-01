"""issue.bitable_record_id (all issues mirror to the Bitable)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-17 03:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issue", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bitable_record_id", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issue", schema=None) as batch_op:
        batch_op.drop_column("bitable_record_id")
