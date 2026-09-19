"""Shared bounded-retry backoff for Celery tasks and outbound HTTP calls.

ReportJob retries (worker/tasks.py) and WebhookDelivery retries
(webhook_service.py) previously duplicated the same "30 seconds" backoff
as two separately named constants that a comment on each promised to
"keep in sync deliberately" — exactly the kind of drift a shared
constant exists to prevent. Each domain keeps its own attempt ceiling
(MAX_JOB_ATTEMPTS, MAX_DELIVERY_ATTEMPTS) since those bounds are
independent policy decisions, not duplicated ones; only the backoff
delay and the outbound HTTP timeout are actually shared.

Neither retry path uses Celery's own `autoretry_for`/`retry_backoff` —
both call `apply_async(countdown=...)` (jobs) or rely on a periodic
sweep keyed off `next_attempt_at` (webhooks) explicitly instead, so
attempts are bounded in exactly one place per domain. Adding a Celery
retry decorator on top of either would double the effective retry
count; don't.
"""

from datetime import timedelta

# Backoff between a retryable failure and the next attempt, for both
# ReportJob re-execution and WebhookDelivery redispatch.
RETRY_BACKOFF_SECONDS = 30
RETRY_BACKOFF = timedelta(seconds=RETRY_BACKOFF_SECONDS)

# Timeout for outbound HTTP calls this service makes to operator-configured
# destinations (webhooks). Bounded so one slow/hanging destination can't
# tie up a worker indefinitely.
OUTBOUND_HTTP_TIMEOUT_SECONDS = 15.0
