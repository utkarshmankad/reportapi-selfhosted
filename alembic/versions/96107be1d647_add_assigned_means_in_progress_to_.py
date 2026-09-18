"""add assigned means in progress to schedules

Revision ID: 96107be1d647
Revises: e53b38e592f8
Create Date: 2026-09-18 23:48:48.715702

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96107be1d647"
down_revision: Union[str, Sequence[str], None] = "e53b38e592f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "schedules",
        sa.Column(
            "assigned_means_in_progress", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("schedules", "assigned_means_in_progress")
