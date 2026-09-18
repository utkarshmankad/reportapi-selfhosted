# Sprint 1 — Protect data and make setup trustworthy

Scope follows the six Sprint 1 tasks in the repository review roadmap.

| Task | Delivered | Regression evidence |
|---|---|---|
| S1-01 · Feature · P0 | Token authentication across data routes, in-memory UI token, loopback Compose bindings, production startup requirement | Route matrix, settings tests, authenticated browser smoke |
| S1-02 · Bug · P0 | Original-span card filtering, IPv4/IPv6, report-local assignee aliases, all outbound fields filtered | All four providers' captured HTTP request bodies; cross-ticket names and priority coverage |
| S1-03 · Bug · P0 | Operator origin allowlists on save/test/runtime, DNS-pinned sockets with verified TLS, no redirects; isolated bounded rendering and denied resource fetching | Transport-level DNS/redirect/TLS tests; timeout, input/output and Linux memory tests; normal PDF smoke |
| S1-04 · Bug · P1 | Asana/GitHub credential saves with restricted keys | HTTP save tests, newline/key rejection, quoted-literal roundtrips |
| S1-05 · Bug · P1 | Shared durable config, atomic locked writes, repaired permissions, per-job snapshots, external-secret read-only mode | Concurrent process saves; snapshot/precedence tests; API/worker recreation smoke; read-only UI test |
| S1-06 · Tech debt · P1 | Safety regression suite in required CI; locked dependency audits; corrected privacy/deployment docs | Python/frontend coverage gates, integration tests, security scans, full-stack smoke |

Validation is recorded by the pull request's required GitHub Actions checks.
Local macOS tests skip only the Linux address-space regression; the Linux CI
unit job runs it. No new database migration is needed.

## Upgrade actions

1. Set `JIRA_ALLOWED_ORIGINS` to the exact Jira origin on API, worker and beat.
2. For custom Ollama hosts, set `OLLAMA_ALLOWED_ORIGINS`; add the same origin to
   `OUTBOUND_PRIVATE_ORIGINS` only when private-network access is intended.
3. Set `APP_ENV=production` and `CONFIG_API_TOKEN` for production deployments.
4. Retain the shared runtime config volume when recreating services. For external
   secret management, set `CONFIG_READ_ONLY=true` and configure environment secrets.
5. Keep templates within the documented limits; linked or data-URL assets are denied.

See [security boundaries](security-boundaries.md) and [CI commands](ci.md).

## Later sprints

Connector pagination/status mapping/input budgets, durable queued manual jobs,
scheduler concurrency/recovery, richer report provenance, delivery integrations,
and supported Helm deployment remain in Sprints 2–6. Sprint 1 does not claim
complete anonymization or a general-purpose OS sandbox.
