"""Real DB report profile CRUD, uniqueness, and generate-from-profile."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.config import settings
from app.connectors.base import FetchResult
from app.db.models import Report, ReportProfile
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.ticket import Ticket

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Report))
        await db.execute(delete(ReportProfile))
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_duplicate_profile_name_is_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/api/report-profiles",
            json={"name": "Weekly demo", "connector": "jira", "board_id": "DEMO"},
        )
        assert first.status_code == 200

        second = await client.post(
            "/api/report-profiles",
            json={"name": "Weekly demo", "connector": "jira", "board_id": "OTHER"},
        )
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_generate_from_profile_uses_stored_scope_and_format(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(settings, "github_pat", "test")
    monkeypatch.setattr(settings, "openai_api_key", "test")
    monkeypatch.setattr(
        "app.connectors.github.GitHubConnector.fetch",
        AsyncMock(
            return_value=FetchResult(
                tickets=[
                    Ticket(
                        id="1",
                        title="Ship it",
                        description="",
                        status="done",
                        assignee=None,
                        priority=None,
                        labels=[],
                        created_at=now,
                        updated_at=now,
                        url="https://example.com",
                        sprint=None,
                    )
                ]
            )
        ),
    )
    monkeypatch.setattr(
        "app.llm.openai_provider.OpenAIProvider.generate",
        AsyncMock(return_value=("Shipped.", 10, False)),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/report-profiles",
            json={
                "name": "GitHub weekly",
                "connector": "github",
                "board_id": "acme/widgets",
                "output_format": "markdown",
            },
        )
        assert created.status_code == 200
        profile_id = created.json()["id"]

        generated = await client.post(f"/api/report-profiles/{profile_id}/generate", json={})
        assert generated.status_code == 200
        body = generated.json()
        assert body["narrative"] == "Shipped."
        assert body["output_format"] == "markdown"
