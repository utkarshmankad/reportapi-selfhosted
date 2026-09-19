"""add schedule timezone

Revision ID: 9eb1b43e4274
Revises: a3fdec125f69
Create Date: 2026-09-19 10:26:37.723020

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9eb1b43e4274"
down_revision: Union[str, Sequence[str], None] = "a3fdec125f69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing schedules were always UTC (no timezone concept existed
    # before this migration) — backfill preserves that exact behavior.
    op.add_column(
        "schedules",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("schedules", "timezone")
