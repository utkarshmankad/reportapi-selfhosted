"""Real Postgres tests for report retention enforcement (S5-03)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.retention_service import enforce_report_retention
from app.db.models import Report, WebhookDelivery, WebhookDestination
from app.db.session import AsyncSessionLocal

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WebhookDelivery))
        await db.execute(delete(Report))
        await db.execute(delete(WebhookDestination))
        await db.commit()
    yield


async def _make_report(db, age_days: int) -> Report:
    report = Report(
        connector="jira",
        board_id="PROJ",
        status="complete",
        model_used="openai",
        tokens_used=1,
        ticket_count=1,
        narrative="ok",
        output_format="text",
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@pytest.mark.asyncio
async def test_old_reports_are_deleted_recent_ones_kept():
    async with AsyncSessionLocal() as db:
        old = await _make_report(db, age_days=10)
        recent = await _make_report(db, age_days=1)

        deleted = await enforce_report_retention(db, retention_days=7)

        assert deleted == 1
        remaining = (await db.execute(select(Report.id))).scalars().all()
        assert old.id not in remaining
        assert recent.id in remaining


@pytest.mark.asyncio
async def test_report_with_pending_delivery_is_never_deleted():
    async with AsyncSessionLocal() as db:
        old = await _make_report(db, age_days=30)
        destination = WebhookDestination(
            name="hook", url="https://hooks.example.com/x", secret="s", active=True
        )
        db.add(destination)
        await db.commit()
        await db.refresh(destination)
        delivery = WebhookDelivery(
            destination_id=destination.id, report_id=old.id, status="pending", payload="{}"
        )
        db.add(delivery)
        await db.commit()

        deleted = await enforce_report_retention(db, retention_days=7)

        assert deleted == 0
        remaining = (await db.execute(select(Report.id))).scalars().all()
        assert old.id in remaining


@pytest.mark.asyncio
async def test_report_with_delivered_delivery_is_still_deleted():
    async with AsyncSessionLocal() as db:
        old = await _make_report(db, age_days=30)
        destination = WebhookDestination(
            name="hook", url="https://hooks.example.com/x", secret="s", active=True
        )
        db.add(destination)
        await db.commit()
        await db.refresh(destination)
        delivery = WebhookDelivery(
            destination_id=destination.id, report_id=old.id, status="delivered", payload="{}"
        )
        db.add(delivery)
        await db.commit()

        deleted = await enforce_report_retention(db, retention_days=7)

        assert deleted == 1
        remaining = (await db.execute(select(Report.id))).scalars().all()
        assert old.id not in remaining


@pytest.mark.asyncio
async def test_zero_or_negative_retention_days_disables_enforcement():
    async with AsyncSessionLocal() as db:
        old = await _make_report(db, age_days=3650)

        assert await enforce_report_retention(db, retention_days=0) == 0
        assert await enforce_report_retention(db, retention_days=-1) == 0

        remaining = (await db.execute(select(Report.id))).scalars().all()
        assert old.id in remaining
