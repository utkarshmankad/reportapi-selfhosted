"""Real Postgres tests for the webhook outbox and delivery pipeline (S5-01)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.ssrf_guard import UnsafeURLError
from app.core.webhook_service import (
    MAX_DELIVERY_ATTEMPTS,
    enqueue_deliveries_for_report,
    retry_delivery,
    send_delivery,
    sign_payload,
)
from app.db.models import Report, WebhookDelivery, WebhookDestination
from app.db.session import AsyncSessionLocal

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _clean_webhook_tables():
    # These tests assert on "every active destination"/"deliveries for this
    # report" counts, which only hold if the tables start empty — this
    # suite has no transactional-rollback isolation between tests, so
    # another test's (or another file's) leftover rows would otherwise
    # silently inflate these counts.
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WebhookDelivery))
        await db.execute(delete(WebhookDestination))
        await db.commit()
    yield


async def _make_report(db) -> Report:
    report = Report(
        connector="jira",
        board_id="PROJ",
        status="complete",
        model_used="openai",
        tokens_used=10,
        ticket_count=3,
        narrative="ok",
        output_format="text",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def _make_destination(db, active=True) -> WebhookDestination:
    destination = WebhookDestination(
        name="Test hook",
        url="https://hooks.example.com/x",
        secret="topsecret",
        active=active,
    )
    db.add(destination)
    await db.commit()
    await db.refresh(destination)
    return destination


@pytest.mark.asyncio
async def test_enqueue_creates_one_delivery_per_active_destination():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        active_a = await _make_destination(db)
        active_b = await _make_destination(db)
        await _make_destination(db, active=False)

        deliveries = await enqueue_deliveries_for_report(db, report)
        await db.commit()

        assert len(deliveries) == 2
        destination_ids = {d.destination_id for d in deliveries}
        assert destination_ids == {active_a.id, active_b.id}
        assert all(d.status == "pending" for d in deliveries)
        payload = json.loads(deliveries[0].payload)
        assert payload["report_id"] == str(report.id)
        assert payload["ticket_count"] == 3


@pytest.mark.asyncio
async def test_send_delivery_success_marks_delivered_and_signs_payload():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        await _make_destination(db)
        deliveries = await enqueue_deliveries_for_report(db, report)
        await db.commit()
        delivery = deliveries[0]

    captured = {}

    class FakeResponse:
        status_code = 200

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return FakeResponse()

    with (
        patch("app.core.webhook_service.target_policy", return_value=False),
        patch("app.core.webhook_service.safe_client", return_value=FakeClient()),
    ):
        async with AsyncSessionLocal() as db:
            delivery = await db.get(WebhookDelivery, delivery.id)
            result = await send_delivery(db, delivery)

    assert result.status == "delivered"
    assert result.response_status == 200
    assert result.delivered_at is not None
    expected_signature = sign_payload("topsecret", captured["content"])
    assert captured["headers"]["X-Webhook-Signature"] == expected_signature
    assert captured["headers"]["X-Webhook-Delivery-Id"] == str(delivery.id)


@pytest.mark.asyncio
async def test_duplicate_delivery_messages_only_send_once():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        await _make_destination(db)
        deliveries = await enqueue_deliveries_for_report(db, report)
        await db.commit()
        delivery_id = deliveries[0].id

    entered = asyncio.Event()
    release = asyncio.Event()
    sends = 0

    class FakeResponse:
        status_code = 200

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *_args, **_kwargs):
            nonlocal sends
            sends += 1
            entered.set()
            await release.wait()
            return FakeResponse()

    async def execute():
        async with AsyncSessionLocal() as db:
            delivery = await db.get(WebhookDelivery, delivery_id)
            return await send_delivery(db, delivery)

    with (
        patch("app.core.webhook_service.target_policy", return_value=False),
        patch("app.core.webhook_service.safe_client", return_value=FakeClient()),
    ):
        first = asyncio.create_task(execute())
        await entered.wait()
        duplicate = await execute()
        assert duplicate.status == "sending"
        release.set()
        result = await first

    assert sends == 1
    assert result.status == "delivered"
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_send_delivery_failure_retries_then_terminally_fails():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        await _make_destination(db)
        deliveries = await enqueue_deliveries_for_report(db, report)
        await db.commit()
        delivery_id = deliveries[0].id

    with patch(
        "app.core.webhook_service.target_policy",
        side_effect=UnsafeURLError("blocked"),
    ):
        for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
            async with AsyncSessionLocal() as db:
                delivery = await db.get(WebhookDelivery, delivery_id)
                if delivery.next_attempt_at is not None:
                    delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                    await db.commit()
                result = await send_delivery(db, delivery)
            assert result.attempts == attempt
            if attempt < MAX_DELIVERY_ATTEMPTS:
                assert result.status == "pending"
                assert result.next_attempt_at is not None
            else:
                assert result.status == "failed"
                assert result.next_attempt_at is None


@pytest.mark.asyncio
async def test_manual_retry_resets_terminally_failed_delivery():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        destination = await _make_destination(db)
        delivery = WebhookDelivery(
            destination_id=destination.id,
            report_id=report.id,
            status="failed",
            payload="{}",
            attempts=MAX_DELIVERY_ATTEMPTS,
            next_attempt_at=None,
        )
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        result = await retry_delivery(db, delivery)
        assert result.status == "pending"
        assert result.last_error is None


@pytest.mark.asyncio
async def test_send_delivery_to_deactivated_destination_fails_immediately():
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        destination = await _make_destination(db, active=False)
        delivery = WebhookDelivery(
            destination_id=destination.id,
            report_id=report.id,
            status="pending",
            payload="{}",
        )
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        result = await send_delivery(db, delivery)
        assert result.status == "failed"
        assert "deactivated" in result.last_error or "deleted" in result.last_error


@pytest.mark.asyncio
async def test_disallowed_origin_blocks_delivery():
    """The operator allowlist is enforced at delivery time too, not just
    creation — a destination approved under one allowlist config must not
    silently succeed if the allowlist is later tightened."""
    async with AsyncSessionLocal() as db:
        report = await _make_report(db)
        destination = WebhookDestination(
            name="No longer allowed",
            url="https://not-allowed.example.com/x",
            secret="s",
            active=True,
        )
        db.add(destination)
        await db.commit()
        await db.refresh(destination)
        delivery = WebhookDelivery(
            destination_id=destination.id,
            report_id=report.id,
            status="pending",
            payload="{}",
        )
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        result = await send_delivery(db, delivery)
        assert result.status == "pending"
        assert result.attempts == 1
