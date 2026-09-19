"""Real Postgres/Redis tests for the operational status endpoint (S5-06)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.models import Report, ReportJob, WebhookDelivery, WebhookDestination
from app.db.session import AsyncSessionLocal
from app.main import app

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WebhookDelivery))
        await db.execute(delete(ReportJob))
        await db.execute(delete(Report))
        await db.execute(delete(WebhookDestination))
        await db.commit()
    yield


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr("app.config.settings.config_api_token", "test-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_ops_status_reports_job_and_delivery_counts(client):
    async with AsyncSessionLocal() as db:
        db.add(
            ReportJob(
                connector="jira",
                board_id="PROJ",
                status="queued",
                attempts=0,
            )
        )
        db.add(
            ReportJob(
                connector="jira",
                board_id="PROJ",
                status="running",
                attempts=1,
                started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
        )
        await db.commit()

    resp = await client.get("/api/ops/status", headers={"X-Config-Token": "test-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs"]["queued"] == 1
    assert body["jobs"]["running"] == 1
    assert body["jobs"]["stuck"] == 1
    assert body["webhook_deliveries"]["pending"] == 0
    assert "scheduler" in body
    assert body["retention"]["retention_days"] >= 0


@pytest.mark.asyncio
async def test_ops_status_requires_config_token(client):
    resp = await client.get("/api/ops/status")
    assert resp.status_code == 401
