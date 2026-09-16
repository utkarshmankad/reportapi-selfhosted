"""Run inside CI API container: real HTTP, database, Redis and Celery execution."""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.db.models import Report, Schedule
from app.db.session import AsyncSessionLocal, engine
from app.worker.tasks import run_due_schedules


def main():
    base_url = os.environ.get("SMOKE_API_URL", "http://api:8000")
    with httpx.Client(
        base_url=base_url, headers={"X-Config-Token": "smoke-test-token"}, timeout=120
    ) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert httpx.get(f"{base_url}/api/reports").status_code == 401
        result = client.post("/api/report/generate", json={"connector": "jira", "board_id": "DEMO"})
        result.raise_for_status()
        report_id = result.json()["report_id"]
        assert result.json()["ticket_count"] == 1
        assert client.get(f"/api/report/{report_id}/render?format=pdf").content.startswith(b"%PDF")
        template = client.post(
            "/api/templates", json={"name": "Smoke", "content": "<h1>{{ report.narrative }}</h1>"}
        )
        template.raise_for_status()
        assert client.delete(f"/api/templates/{template.json()['id']}").status_code == 204

    async def seed():
        async with AsyncSessionLocal() as db:
            schedule = Schedule(
                connector="jira",
                board_id="DEMO",
                cron_expression="* * * * *",
                output_format="text",
                active=True,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            )
            db.add(schedule)
            await db.commit()
            return schedule.id

    schedule_id = asyncio.run(seed_and_dispose(seed))
    # Round trip through a real worker; no eager mode or direct task call.
    assert run_due_schedules.delay().get(timeout=90) >= 0

    async def verify():
        async with AsyncSessionLocal() as db:
            schedule = await db.get(Schedule, schedule_id)
            assert schedule.last_run_at is not None
            rows = (await db.execute(select(Report))).scalars().all()
            assert len(rows) >= 2
            await db.delete(schedule)
            await db.commit()

    asyncio.run(seed_and_dispose(verify))
    print("HTTP, PDF, database and Celery smoke passed")


async def seed_and_dispose(operation):
    try:
        return await operation()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
