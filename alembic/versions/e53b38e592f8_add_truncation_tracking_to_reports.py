"""add truncation tracking to reports

Revision ID: e53b38e592f8
Revises: 4b652dd146c4
Create Date: 2026-09-18 23:39:35.136117

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e53b38e592f8"
down_revision: Union[str, Sequence[str], None] = "4b652dd146c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "reports",
        sa.Column("is_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("reports", sa.Column("truncation_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reports", "truncation_reason")
    op.drop_column("reports", "is_truncated")
