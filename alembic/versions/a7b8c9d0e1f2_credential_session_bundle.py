"""credential.session_bundle: reusable captured session for password accounts

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-14 06:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as b:
        b.add_column(sa.Column("session_bundle", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as b:
        b.drop_column("session_bundle")
