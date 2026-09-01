"""test_case professional fields

Revision ID: 8d2f3b5c6e21
Revises: 7c1e2a9b4d10
Create Date: 2026-08-11 10:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8d2f3b5c6e21"
down_revision: Union[str, None] = "7c1e2a9b4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("test_case", schema=None) as batch_op:
        batch_op.add_column(sa.Column("case_key", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("module", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("priority", sa.String(length=10), nullable=False, server_default="P2")
        )
        batch_op.add_column(
            sa.Column("type", sa.String(length=20), nullable=False, server_default="functional")
        )
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active")
        )
        batch_op.add_column(sa.Column("owner", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("references", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(
            sa.Column("preconditions", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("steps", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("test_data", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("test_case", schema=None) as batch_op:
        for col in (
            "updated_at",
            "test_data",
            "steps",
            "preconditions",
            "references",
            "owner",
            "status",
            "type",
            "priority",
            "module",
            "case_key",
        ):
            batch_op.drop_column(col)
