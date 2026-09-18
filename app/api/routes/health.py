"""Liveness (`/health`) and dependency readiness (`/health/ready`)."""

from datetime import datetime, timezone

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])

# Redis key the scheduler beat tick writes to on every successful pass —
# used to detect a stalled/dead beat process, not just a dead API.
SCHEDULER_HEARTBEAT_KEY = "reportapi:scheduler:last_tick"
# A beat tick every minute; more than 3x that gap with no update means the
# beat process itself is down, not just mid-cycle.
SCHEDULER_STALE_AFTER_SECONDS = 180


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check() -> dict:
    checks = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unreachable"

    try:
        client = Redis.from_url(settings.redis_url)
        try:
            await client.ping()
            checks["redis"] = "ok"
        finally:
            await client.aclose()
    except Exception:
        checks["redis"] = "unreachable"

    checks["scheduler"] = await _scheduler_freshness()

    healthy = all(value in ("ok", "unknown") for value in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}


async def _scheduler_freshness() -> str:
    try:
        client = Redis.from_url(settings.redis_url)
        try:
            last_tick = await client.get(SCHEDULER_HEARTBEAT_KEY)
        finally:
            await client.aclose()
    except Exception:
        return "unknown"

    if last_tick is None:
        return "unknown"

    last_tick_at = datetime.fromtimestamp(float(last_tick), tz=timezone.utc)
    age = (datetime.now(timezone.utc) - last_tick_at).total_seconds()
    return "ok" if age < SCHEDULER_STALE_AFTER_SECONDS else "stale"
