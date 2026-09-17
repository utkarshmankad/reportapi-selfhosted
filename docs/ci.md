# CI and local verification

GitHub Actions runs on pull requests, pushes to main/develop, manual dispatch, and weekly vulnerability checks. Pull requests from forks use read-only repository permissions and synthetic test credentials. Image publication only follows a successful main-branch push; it never runs on pull requests.

## Mandatory gates

- **Code quality**: locked Poetry metadata, Ruff lint/format, TypeScript strict checking, ESLint, Prettier and a production Next.js build.
- **Unit tests**: every module under `app` is included, including unimported modules. Combined line/branch coverage must be at least **80%**; XML is uploaded even on failure. No application modules are excluded to inflate coverage.
- **Frontend tests and 80% coverage**: Vitest + Testing Library exercise screens, API helpers and the server proxy. Statements, branches, functions and lines must each reach **80%**. Layout metadata and CSS are covered by the production build/browser smoke rather than executable coverage.
- **Integration tests**: real Postgres/Redis; Alembic upgrade and model/schema drift check; persisted report generation with mocked external APIs, PDF rendering, CRUD and Redis roundtrip.
- **End-to-end (docker compose)**: isolated standalone stack with synthetic Jira/Ollama, auth checks, HTTP generation, PDF, database persistence, a real Celery queue/worker roundtrip, and Playwright journeys through all four screens. Ports 18000/18080 must be free. The test uses a unique Compose project and removes only its own resources.
- **Security scan**: Bandit, `pip-audit` inside the installed application environment, and `npm audit` at moderate severity or above. Findings fail CI; no blanket suppression or `continue-on-error` is used. A dependency with no safe fix must be removed or triaged explicitly rather than silently waived.
- **CI required**: an aggregate status fails if any gate fails, is cancelled, or is skipped. The original four check names are preserved for existing branch protection. Require `CI required` in branch protection to enforce the added quality and frontend gates too.

## Run locally

Use Python 3.12, Poetry 2.4.1, Node 22 and Docker Compose v2. WeasyPrint also requires Pango (installed by CI and the engine Dockerfile).

```bash
poetry install --no-root
poetry check --lock
poetry run ruff check app tests scripts alembic
poetry run ruff format --check app tests scripts alembic
poetry run pytest tests --ignore=tests/integration --cov=app --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=80
npm --prefix config-ui ci
npm --prefix config-ui run typecheck
npm --prefix config-ui run lint
npm --prefix config-ui run format:check
npm --prefix config-ui run test:coverage
npm --prefix config-ui run build
poetry run bandit -r app -ll
poetry run pip-audit --progress-spinner=off
npm --prefix config-ui audit --audit-level=moderate
```

For integration, point `DATABASE_URL` and `REDIS_URL` at disposable test services, then run:

```bash
poetry run alembic upgrade head
poetry run alembic check
poetry run pytest tests/integration -m integration -v
```

For the isolated full smoke test:

```bash
(cd config-ui && npx playwright install chromium)
./scripts/e2e-smoke.sh
```

The smoke script neither copies nor changes `.env`. It does not touch the default Compose project's database or volumes. Browser traces/screenshots are saved on failure. Fixed host ports avoid collisions with the default application ports but should not be shared by concurrent local smoke runs.

## Configuration and screen changes

The UI provides Connections, Reports, Schedules and Templates screens. `CONFIG_API_TOKEN`, when set, protects all data endpoints; enter it in **API access**. The UI holds it in memory only. Page refresh clears it. A Next.js server route forwards to runtime `API_INTERNAL_URL`; browser assets contain no credentials or deployment hostname.

Credential saves write a dedicated `CONFIG_STORE_PATH` (default `runtime-config.env`), not the infrastructure `.env`. Compose shares the file using the `runtime_config` volume. Writes are locked, atomic, quoted and owner-only. New report runs reload saved connector/provider overrides. Infrastructure URLs and the API access token remain environment-managed. Back up this volume securely with the database. On Kubernetes, configuration persistence still needs an operator-provided shared writable path; the full Helm deployment remains roadmap work.

Reports currently generate within the HTTP request. The screen displays progress until it completes; it is not a durable background-job UI. Schedules run in UTC and show **last attempt**, not a guaranteed successful run. Output templates affect PDF downloads; they are not accepted silently at generation time. PDF external images/stylesheets are disabled.

Unused Chroma and JWT dependency scaffolding was removed to eliminate vulnerable packages without affecting the implemented report pipeline. WeasyPrint and Next.js were updated to patched versions. Known connector pagination, scheduler concurrency, report provenance and Helm dependency gaps from the roadmap remain separate work.


## Sprint 1 regressions

Unit coverage includes every registered data route's auth boundary, all four
providers' captured request bodies, formatted cards/IPs/assignee aliases,
operator destination allowlists, DNS rebinding, numeric dialing with TLS hostname
verification, redirects, response limits, renderer limits, concurrent config
writers, literal secrets and per-job snapshots. Coverage includes render subprocesses.
The Linux CI run additionally verifies the renderer's address-space limit.

The Compose smoke stack starts in production with an instance token and an
unconfigured cloud provider. It saves Ollama configuration and a synthetic GitHub
credential through HTTP, recreates API/worker/beat while retaining only its own
shared volume, and verifies saved configuration through API generation and a real
Celery roundtrip. This detects accidental fallback to the startup provider.
