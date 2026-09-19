"""add template versioning and report/job source, ticket count, prompt and template linkage

Revision ID: 1de0e393db54
Revises: 32db7040007d
Create Date: 2026-09-19 05:28:37.454120

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1de0e393db54"
down_revision: Union[str, Sequence[str], None] = "32db7040007d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("report_jobs", sa.Column("template_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_report_jobs_template_id",
        "report_jobs",
        "report_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "report_templates",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "report_templates",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("reports", sa.Column("board_id", sa.String(length=100), nullable=True))
    op.add_column("reports", sa.Column("sprint_id", sa.String(length=100), nullable=True))
    op.add_column(
        "reports", sa.Column("ticket_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "reports", sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("reports", sa.Column("template_id", sa.UUID(), nullable=True))
    op.add_column("reports", sa.Column("template_version", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("template_snapshot", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_reports_template_id",
        "reports",
        "report_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_reports_template_id", "reports", type_="foreignkey")
    op.drop_column("reports", "template_snapshot")
    op.drop_column("reports", "template_version")
    op.drop_column("reports", "template_id")
    op.drop_column("reports", "prompt_version")
    op.drop_column("reports", "ticket_count")
    op.drop_column("reports", "sprint_id")
    op.drop_column("reports", "board_id")
    op.drop_column("report_templates", "archived")
    op.drop_column("report_templates", "version")
    op.drop_constraint("fk_report_jobs_template_id", "report_jobs", type_="foreignkey")
    op.drop_column("report_jobs", "template_id")
