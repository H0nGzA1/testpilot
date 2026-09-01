"""multi-account roles: credential.role, test_case.role, project.roles

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-13 03:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as b:
        b.add_column(sa.Column("role", sa.String(length=60), nullable=True))
    with op.batch_alter_table("test_case", schema=None) as b:
        b.add_column(sa.Column("role", sa.String(length=60), nullable=True))
    with op.batch_alter_table("project", schema=None) as b:
        b.add_column(sa.Column("roles", sa.JSON(), nullable=True))
    with op.batch_alter_table("run_result", schema=None) as b:
        b.add_column(sa.Column("account_label", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("run_result", schema=None) as b:
        b.drop_column("account_label")
    with op.batch_alter_table("project", schema=None) as b:
        b.drop_column("roles")
    with op.batch_alter_table("test_case", schema=None) as b:
        b.drop_column("role")
    with op.batch_alter_table("credential", schema=None) as b:
        b.drop_column("role")
