"""add report profiles

Revision ID: fa061d481005
Revises: b714a65f3e2c
Create Date: 2026-09-22 00:31:33.905854

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa061d481005"
down_revision: Union[str, Sequence[str], None] = "b714a65f3e2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "report_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("connector", sa.String(length=50), nullable=False),
        sa.Column("board_id", sa.String(length=100), nullable=True),
        sa.Column("sprint_id", sa.String(length=100), nullable=True),
        sa.Column("output_format", sa.String(length=20), nullable=False),
        sa.Column("assigned_means_in_progress", sa.Boolean(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["report_templates.id"],
            name="fk_report_profiles_template_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_report_profiles"),
        sa.UniqueConstraint("name", name="uq_report_profiles_name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("report_profiles")
