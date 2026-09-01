"""feishu bitable per-project sync columns

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-17 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(sa.Column("feishu_bitable_app_token", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("feishu_bitable_table_id", sa.String(120), nullable=True))
    with op.batch_alter_table("feedback_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bitable_record_id", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("feedback_item", schema=None) as batch_op:
        batch_op.drop_column("bitable_record_id")
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("feishu_bitable_table_id")
        batch_op.drop_column("feishu_bitable_app_token")
