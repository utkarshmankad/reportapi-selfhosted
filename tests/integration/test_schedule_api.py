"""Integration test — real Postgres, real FastAPI app via ASGI transport,
no mocking. Exercises the Schedule CRUD path end to end.
"""

import httpx
import pytest
from httpx import ASGITransport

from app.main import app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_create_list_delete_schedule():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        create_res = await client.post(
            "/api/schedule",
            json={
                "connector": "jira",
                "board_id": "PROJ",
                "cron_expression": "0 9 * * 1",
                "output_format": "text",
            },
        )
        assert create_res.status_code == 200
        schedule = create_res.json()
        assert schedule["board_id"] == "PROJ"
        assert schedule["active"] is True

        list_res = await client.get("/api/schedule")
        assert list_res.status_code == 200
        assert any(s["id"] == schedule["id"] for s in list_res.json())

        delete_res = await client.delete(f"/api/schedule/{schedule['id']}")
        assert delete_res.status_code == 204

        list_after = await client.get("/api/schedule")
        assert not any(s["id"] == schedule["id"] for s in list_after.json())


@pytest.mark.asyncio
async def test_rejects_invalid_cron_expression():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/schedule",
            json={
                "connector": "jira",
                "board_id": "PROJ",
                "cron_expression": "not a cron",
            },
        )
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_rejects_missing_board_and_sprint():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/schedule",
            json={
                "connector": "jira",
                "cron_expression": "0 9 * * 1",
            },
        )
        assert res.status_code == 422
