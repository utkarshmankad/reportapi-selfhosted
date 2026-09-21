"""Signed webhook delivery via a transactional outbox.

A delivery row is created in the same transaction as the report success
that triggers it (see enqueue_deliveries_for_report, called from
job_service.run_job). The actual HTTP call happens later, in a separate
task/transaction — a worker crash between those two steps leaves a
`pending` row a delivery task can still find and send, instead of losing
the notification the way an inline fire-and-forget call would.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.core.retry_policy import OUTBOUND_HTTP_TIMEOUT_SECONDS, RETRY_BACKOFF
from app.core.ssrf_guard import UnsafeURLError, safe_client, target_policy
from app.db.models import (
    DELIVERY_STATUS_DELIVERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SENDING,
    Report,
    WebhookDelivery,
    WebhookDestination,
)

logger = get_logger(__name__)

# Bounded like ReportJob's MAX_JOB_ATTEMPTS, for the same reason: a
# permanently-unreachable destination shouldn't retry forever. A manual
# retry (POST /api/webhooks/deliveries/{id}/retry) bypasses this bound
# explicitly, since that's an operator decision, not an automatic one.
MAX_DELIVERY_ATTEMPTS = 5
DELIVERY_LEASE = timedelta(minutes=10)

# Retry delay for a failed attempt with attempts remaining — shared with
# ReportJob's retry backoff via app.core.retry_policy (see S5-05).
RETRY_DELAY = RETRY_BACKOFF

SIGNATURE_HEADER = "X-Webhook-Signature"
DELIVERY_ID_HEADER = "X-Webhook-Delivery-Id"


def sign_payload(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _report_payload(report: Report) -> dict:
    return {
        "event": "report.succeeded" if report.status != "partial" else "report.partial",
        "report_id": str(report.id),
        "connector": report.connector,
        "board_id": report.board_id,
        "sprint_id": report.sprint_id,
        "status": report.status,
        "ticket_count": report.ticket_count,
        "is_truncated": report.is_truncated,
        "output_format": report.output_format,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def enqueue_deliveries_for_report(db: AsyncSession, report: Report) -> list[WebhookDelivery]:
    """
    Create one pending delivery per active destination. Called from within
    the same transaction that persists the report/job success, so a
    delivery is never created for a report that ultimately failed to
    commit, and never silently skipped for one that did.
    """
    result = await db.execute(select(WebhookDestination).where(WebhookDestination.active.is_(True)))
    destinations = list(result.scalars().all())
    if not destinations:
        return []

    payload = json.dumps(_report_payload(report), sort_keys=True)
    deliveries = [
        WebhookDelivery(destination_id=d.id, report_id=report.id, payload=payload)
        for d in destinations
    ]
    for delivery in deliveries:
        db.add(delivery)
    await db.flush()
    for delivery in deliveries:
        await db.refresh(delivery)
    return deliveries


async def send_delivery(db: AsyncSession, delivery: WebhookDelivery) -> WebhookDelivery:
    """
    Execute one delivery attempt in the caller's session scope — mirrors
    job_service.run_job: the caller (a Celery task) is responsible for
    using a session scoped to just this delivery, so one destination's
    failure can't affect another's transaction.
    """
    now = datetime.now(timezone.utc)
    claimed = await db.execute(
        update(WebhookDelivery)
        .where(
            WebhookDelivery.id == delivery.id,
            or_(
                and_(
                    WebhookDelivery.status == DELIVERY_STATUS_PENDING,
                    or_(
                        WebhookDelivery.next_attempt_at.is_(None),
                        WebhookDelivery.next_attempt_at <= now,
                    ),
                ),
                and_(
                    WebhookDelivery.status == DELIVERY_STATUS_SENDING,
                    WebhookDelivery.next_attempt_at <= now,
                ),
            ),
        )
        .values(
            status=DELIVERY_STATUS_SENDING,
            attempts=WebhookDelivery.attempts + 1,
            next_attempt_at=now + DELIVERY_LEASE,
        )
        .returning(WebhookDelivery.id)
        .execution_options(synchronize_session=False)
    )
    owns_attempt = claimed.scalar_one_or_none() is not None
    await db.commit()
    if not owns_attempt:
        await db.refresh(delivery)
        logger.info(
            "duplicate webhook delivery execution ignored",
            extra={"delivery_id": str(delivery.id), "status": delivery.status},
        )
        return delivery

    await db.refresh(delivery)
    destination = await db.get(WebhookDestination, delivery.destination_id)

    if destination is None or not destination.active:
        delivery.status = DELIVERY_STATUS_FAILED
        delivery.last_error = "Destination was deleted or deactivated"
        delivery.next_attempt_at = None
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)
        return delivery

    body = delivery.payload.encode()
    signature = sign_payload(destination.secret, body)

    try:
        target_policy(destination.url, "webhook")
        async with safe_client(
            destination.url, "webhook", timeout=OUTBOUND_HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                destination.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    SIGNATURE_HEADER: signature,
                    DELIVERY_ID_HEADER: str(delivery.id),
                },
            )
        delivery.response_status = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = DELIVERY_STATUS_DELIVERED
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.last_error = None
            delivery.next_attempt_at = None
        else:
            raise UnsafeURLError(f"Destination responded with HTTP {response.status_code}")
    except Exception as e:
        delivery.last_error = str(e) if isinstance(e, UnsafeURLError) else "Delivery request failed"
        retryable = delivery.attempts < MAX_DELIVERY_ATTEMPTS
        delivery.status = DELIVERY_STATUS_PENDING if retryable else DELIVERY_STATUS_FAILED
        delivery.next_attempt_at = datetime.now(timezone.utc) + RETRY_DELAY if retryable else None
        logger.warning(
            "webhook delivery attempt failed",
            extra={
                "delivery_id": str(delivery.id),
                "destination_id": str(delivery.destination_id),
                "attempt": delivery.attempts,
                "status": delivery.status,
            },
        )

    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return delivery


async def retry_delivery(db: AsyncSession, delivery: WebhookDelivery) -> WebhookDelivery:
    """Explicit manual retry — resets a terminally-failed delivery back to
    pending regardless of MAX_DELIVERY_ATTEMPTS, since this is an operator
    decision to try again, not an automatic retry."""
    delivery.status = DELIVERY_STATUS_PENDING
    delivery.last_error = None
    delivery.next_attempt_at = None
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return delivery
