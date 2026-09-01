"""run_result.updated_at — heartbeat for the stale-run reconciler

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-31 02:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("run_result", schema=None) as b:
        b.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
    # existing rows: their last real sign of life was creation, not this migration
    op.execute("UPDATE run_result SET updated_at = created_at")


def downgrade() -> None:
    with op.batch_alter_table("run_result", schema=None) as b:
        b.drop_column("updated_at")
