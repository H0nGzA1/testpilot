"""suite loop: test_suite + notification tables, run/issue columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-13 02:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_suite",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("selection_mode", sa.String(length=10), nullable=False, server_default="cases"),
        sa.Column("case_ids", sa.JSON(), nullable=True),
        sa.Column("tag_filter", sa.JSON(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("runner_user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("cadence", sa.String(length=10), nullable=False, server_default="none"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.Integer(), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_test_suite_project_id", "test_suite", ["project_id"])

    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("suite_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("emailed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_user_id", "notification", ["user_id"])
    op.create_index("ix_notification_created_at", "notification", ["created_at"])

    with op.batch_alter_table("run", schema=None) as b:
        b.add_column(sa.Column("suite_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("ran_by_user_id", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column("trigger", sa.String(length=20), nullable=False, server_default="manual")
        )
    op.create_index("ix_run_suite_id", "run", ["suite_id"])

    with op.batch_alter_table("issue", schema=None) as b:
        b.add_column(sa.Column("assignee_user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issue", schema=None) as b:
        b.drop_column("assignee_user_id")
    op.drop_index("ix_run_suite_id", table_name="run")
    with op.batch_alter_table("run", schema=None) as b:
        b.drop_column("trigger")
        b.drop_column("ran_by_user_id")
        b.drop_column("suite_id")
    op.drop_index("ix_notification_created_at", table_name="notification")
    op.drop_index("ix_notification_user_id", table_name="notification")
    op.drop_table("notification")
    op.drop_index("ix_test_suite_project_id", table_name="test_suite")
    op.drop_table("test_suite")
