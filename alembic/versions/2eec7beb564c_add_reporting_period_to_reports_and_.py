"""add reporting period to reports and schedules

Revision ID: 2eec7beb564c
Revises: 96107be1d647
Create Date: 2026-09-19 00:23:06.390420

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2eec7beb564c"
down_revision: Union[str, Sequence[str], None] = "96107be1d647"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("reports", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("period_semantics", sa.String(length=255), nullable=True))
    op.add_column("schedules", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("schedules", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("schedules", "period_end")
    op.drop_column("schedules", "period_start")
    op.drop_column("reports", "period_semantics")
    op.drop_column("reports", "period_end")
    op.drop_column("reports", "period_start")
