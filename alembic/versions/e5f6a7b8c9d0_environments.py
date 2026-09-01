"""environments: environment table + env_id on credential/run/test_suite

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-13 04:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_environment_project_id", "environment", ["project_id"])
    with op.batch_alter_table("credential", schema=None) as b:
        b.add_column(sa.Column("environment_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("run", schema=None) as b:
        b.add_column(sa.Column("environment_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("test_suite", schema=None) as b:
        b.add_column(sa.Column("environment_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("test_suite", schema=None) as b:
        b.drop_column("environment_id")
    with op.batch_alter_table("run", schema=None) as b:
        b.drop_column("environment_id")
    with op.batch_alter_table("credential", schema=None) as b:
        b.drop_column("environment_id")
    op.drop_index("ix_environment_project_id", table_name="environment")
    op.drop_table("environment")
