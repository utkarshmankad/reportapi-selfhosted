"""Real DB report/template lifecycle, with external providers isolated."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from redis.asyncio import Redis

from app.config import settings
from app.main import app
from app.models.ticket import Ticket

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_report_generation_persistence_export_and_cleanup(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(settings, "github_pat", "test")
    monkeypatch.setattr(settings, "openai_api_key", "test")
    monkeypatch.setattr(
        "app.connectors.github.GitHubConnector.fetch",
        AsyncMock(
            return_value=[
                Ticket(
                    id="1",
                    title="Release",
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
        ),
    )
    monkeypatch.setattr(
        "app.llm.openai_provider.OpenAIProvider.generate",
        AsyncMock(return_value=("Release complete.", 12)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/report/generate", json={"connector": "github", "board_id": "test/repo"}
        )
        assert created.status_code == 200
        report_id = created.json()["report_id"]
        template_id = None
        try:
            assert (await client.get(f"/api/report/{report_id}")).json()[
                "narrative"
            ] == "Release complete."
            assert any(row["id"] == report_id for row in (await client.get("/api/reports")).json())
            template = await client.post(
                "/api/templates",
                json={"name": "Integration", "content": "<h1>{{ report.narrative }}</h1>"},
            )
            assert template.status_code == 200
            template_id = template.json()["id"]
            assert (
                await client.put(
                    f"/api/templates/{template_id}",
                    json={"name": "Updated", "content": "<p>{{ report.narrative }}</p>"},
                )
            ).status_code == 200
            pdf = await client.get(
                f"/api/report/{report_id}/render?format=pdf&template_id={template_id}"
            )
            assert pdf.content.startswith(b"%PDF")
        finally:
            assert (await client.delete(f"/api/report/{report_id}")).status_code == 204
            if template_id:
                assert (await client.delete(f"/api/templates/{template_id}")).status_code == 204
        assert (await client.get(f"/api/report/{report_id}")).status_code == 404


@pytest.mark.asyncio
async def test_redis_roundtrip():
    from uuid import uuid4

    client = Redis.from_url(settings.redis_url)
    key = f"integration:{uuid4()}"
    try:
        assert await client.ping()
        await client.set(key, "ok", ex=30)
        assert await client.get(key) == b"ok"
    finally:
        await client.delete(key)
        await client.aclose()
