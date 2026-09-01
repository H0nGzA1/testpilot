"""feishu feedback_item

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("feishu_message_id", sa.String(length=120), nullable=True),
        sa.Column("chat_id", sa.String(length=120), nullable=True),
        sa.Column("chat_type", sa.String(length=20), nullable=True),
        sa.Column("sender_id", sa.String(length=120), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feishu_message_id", name="uq_feedback_item_feishu_message_id"),
    )
    with op.batch_alter_table("feedback_item", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_feedback_item_project_id"), ["project_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("feedback_item", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_feedback_item_project_id"))
    op.drop_table("feedback_item")
