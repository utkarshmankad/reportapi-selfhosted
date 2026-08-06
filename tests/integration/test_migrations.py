"""Integration tests — require a real Postgres reachable via DATABASE_URL.

CI runs `alembic upgrade head` before this test module, so these assert the
schema that produced rather than re-running the migration themselves.
"""
import pytest
from sqlalchemy import text
from app.db.session import engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_expected_tables_exist():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
        tables = {row[0] for row in result.fetchall()}

    assert {"reports", "schedules", "report_templates", "alembic_version"} <= tables


@pytest.mark.asyncio
async def test_reports_table_has_expected_columns():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name='reports'")
        )
        columns = {row[0] for row in result.fetchall()}

    assert {"id", "connector", "status", "model_used", "tokens_used",
            "narrative", "output_format", "created_at"} <= columns
