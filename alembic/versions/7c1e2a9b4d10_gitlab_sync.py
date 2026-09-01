"""gitlab sync columns

Revision ID: 7c1e2a9b4d10
Revises: 609da2fff72f
Create Date: 2026-08-10 18:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1e2a9b4d10"
down_revision: Union[str, None] = "609da2fff72f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gitlab_project", sa.String(length=400), nullable=True))

    with op.batch_alter_table("issue", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gitlab_iid", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("gitlab_project", sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_sync_hash", sa.String(length=64), nullable=True))

    with op.batch_alter_table("issue_comment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gitlab_note_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issue_comment", schema=None) as batch_op:
        batch_op.drop_column("gitlab_note_id")

    with op.batch_alter_table("issue", schema=None) as batch_op:
        batch_op.drop_column("last_sync_hash")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("gitlab_project")
        batch_op.drop_column("gitlab_iid")

    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("gitlab_project")
