"""accounts / rbac tables

Revision ID: 9f3a1c7d2e40
Revises: 8d2f3b5c6e21
Create Date: 2026-08-11 12:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f3a1c7d2e40"
down_revision: Union[str, None] = "8d2f3b5c6e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    with op.batch_alter_table("app_user", schema=None) as b:
        b.create_index(b.f("ix_app_user_email"), ["email"], unique=True)

    op.create_table(
        "project_member",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("project_member", schema=None) as b:
        b.create_index(b.f("ix_project_member_project_id"), ["project_id"], unique=False)
        b.create_index(b.f("ix_project_member_user_id"), ["user_id"], unique=False)

    op.create_table(
        "invite",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_role", sa.String(length=20), nullable=False, server_default="editor"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    with op.batch_alter_table("invite", schema=None) as b:
        b.create_index(b.f("ix_invite_email"), ["email"], unique=False)
        b.create_index(b.f("ix_invite_token"), ["token"], unique=True)

    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
    with op.batch_alter_table("invite", schema=None) as b:
        b.drop_index(b.f("ix_invite_token"))
        b.drop_index(b.f("ix_invite_email"))
    op.drop_table("invite")
    with op.batch_alter_table("project_member", schema=None) as b:
        b.drop_index(b.f("ix_project_member_user_id"))
        b.drop_index(b.f("ix_project_member_project_id"))
    op.drop_table("project_member")
    with op.batch_alter_table("app_user", schema=None) as b:
        b.drop_index(b.f("ix_app_user_email"))
    op.drop_table("app_user")
