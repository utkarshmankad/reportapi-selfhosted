"""Report retention enforcement.

Deletes reports older than settings.report_retention_days — but never a
report with a still-`pending` webhook delivery. A report's lifecycle
doesn't end when it's generated; it ends when whatever was notified about
it has finished trying, so deleting it out from under a pending delivery
would either break that delivery's payload reference or silently drop
the notification.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.db.models import DELIVERY_STATUS_PENDING, Report, WebhookDelivery

logger = get_logger(__name__)


async def enforce_report_retention(db: AsyncSession, retention_days: int) -> int:
    """
    Delete reports older than `retention_days`, excluding any report with
    a pending webhook delivery. retention_days <= 0 disables enforcement
    entirely (returns 0 without querying) — retention is opt-in, not a
    silent default that could surprise an operator who never set it.
    """
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    pending_report_ids = select(WebhookDelivery.report_id).where(
        WebhookDelivery.status == DELIVERY_STATUS_PENDING
    )
    eligible_ids = (
        (
            await db.execute(
                select(Report.id).where(
                    Report.created_at < cutoff, Report.id.not_in(pending_report_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if not eligible_ids:
        return 0

    await db.execute(delete(Report).where(Report.id.in_(eligible_ids)))
    await db.commit()
    logger.info(
        "enforced report retention",
        extra={"deleted_count": len(eligible_ids), "retention_days": retention_days},
    )
    return len(eligible_ids)
