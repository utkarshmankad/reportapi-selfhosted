"""prevent duplicate webhook deliveries

Revision ID: b714a65f3e2c
Revises: 9eb1b43e4274
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b714a65f3e2c"
down_revision: Union[str, Sequence[str], None] = "9eb1b43e4274"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_webhook_deliveries_destination_report",
        "webhook_deliveries",
        ["destination_id", "report_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_webhook_deliveries_destination_report",
        "webhook_deliveries",
        type_="unique",
    )
