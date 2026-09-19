# Operations runbook

What to check when a deployment looks unhealthy, and what each signal
means. Pairs with `GET /api/ops/status` (requires `X-Config-Token`) and
`GET /health/ready` (unauthenticated, for load balancers/orchestrators).

## Where to look first

```bash
curl http://localhost:8000/health/ready
curl -H "X-Config-Token: $CONFIG_API_TOKEN" http://localhost:8000/api/ops/status
```

`/health/ready` answers "is anything down" (database, Redis, scheduler
freshness). `/api/ops/status` answers "is anything backing up" (queue
depths, stuck jobs, failed deliveries, retention backlog) — check it
second, once `/health/ready` says the basics are up.

## Reading `/api/ops/status`

```json
{
  "scheduler": "ok",
  "jobs": {"queued": 0, "running": 1, "failed": 0, "stuck": 0},
  "webhook_deliveries": {"pending": 0, "failed": 0},
  "retention": {"retention_days": 7, "reports_eligible_for_cleanup": 0}
}
```

| Field | What it means | When to worry |
|---|---|---|
| `scheduler` | Freshness of the last `dispatch_due_schedules` beat tick (see `docs/scheduling.md`) | `stale` or `unknown` for more than a few minutes — the beat process is likely down |
| `jobs.queued` | Report jobs waiting for a worker | Growing without bound — worker pool is undersized or a worker crashed |
| `jobs.running` | Report jobs a worker currently owns | Should track queue throughput; near-zero with high `queued` means workers aren't picking up tasks |
| `jobs.failed` | Jobs that exhausted `MAX_JOB_ATTEMPTS` (3) | Any nonzero value on a connector/provider that used to work — check `error_reason` on the job via `GET /api/report/jobs/{id}` |
| `jobs.stuck` | Jobs `running` longer than `STALE_RUNNING_AFTER` (10 min) | Nonzero — either genuinely slow work or a worker that died without the recovery sweep having run yet (`recover_stuck_report_jobs` runs every 5 minutes) |
| `webhook_deliveries.pending` | Deliveries not yet sent or mid-backoff | Growing without bound — the `dispatch_pending_webhook_deliveries` beat tick or a destination is unreachable |
| `webhook_deliveries.failed` | Deliveries that exhausted `MAX_DELIVERY_ATTEMPTS` (5) | Nonzero — destination is down or rejecting the signed payload; use `POST /api/webhooks/deliveries/{id}/retry` once fixed |
| `retention.reports_eligible_for_cleanup` | Reports older than `REPORT_RETENTION_DAYS` not yet swept | Large and not shrinking — the daily `enforce_report_retention` beat tick (03:00 UTC) isn't running |

## Common incidents

**Scheduler shows `stale`.** The beat process is a separate container/process
from the worker. Check it's running (`docker compose ps beat` or
equivalent) and check its logs for startup errors. A `stale` reading
means the last successful dispatch pass is older than
`SCHEDULER_STALE_AFTER_SECONDS` (3 minutes) — `unknown` means Redis
itself is unreachable or no tick has ever landed.

**`jobs.queued` growing, `jobs.running` flat.** No live worker consuming
the queue. Check worker container logs and Redis connectivity
(`REDIS_URL`) from the worker's environment, not just the API's.

**`jobs.stuck` nonzero and staying nonzero.** `recover_stuck_report_jobs`
should reclaim these within 5 minutes. If the count doesn't drop, the
beat schedule itself may be down (see scheduler check above) — stuck
jobs and a stale scheduler are usually the same root cause.

**`webhook_deliveries.failed` nonzero.** Look at the delivery via
`GET /api/webhooks/deliveries` for `response_status`/`last_error`. Fix
the destination, then `POST /api/webhooks/deliveries/{id}/retry` —
manual retry bypasses `MAX_DELIVERY_ATTEMPTS` deliberately, since
resuming a fixed destination is an operator decision, not an automatic
one.

**`retention.reports_eligible_for_cleanup` keeps climbing.** Either
`REPORT_RETENTION_DAYS` is set to `0` (which disables enforcement by
design — retention is opt-in) or the beat process is down (same check
as above). Note a report with a still-`pending` webhook delivery is
never deleted regardless of age — that's intentional, not a bug.

## Logs

All application logs are structured JSON (see `app/core/logging_config.py`).
Every HTTP error response includes a `request_id` (also on the
`X-Request-Id` response header); grep worker/API logs for that value to
find the exact server-side log line for a reported failure — the
public error body never contains exception details, only that ID.
