# ReportAPI Self-Hosted

Container-native reporting engine for Agile ticket data. Runs entirely
on your own infrastructure — no data leaves your network, and PII is
stripped before any ticket content reaches an LLM.

## Status
v0.5 — Community release. Jira connector · OpenAI/Anthropic/Ollama ·
browser-based config UI · scheduled reports · PDF/Markdown output with
custom templates · Helm chart.

## Quick start

```bash
cp .env.example .env
# Fill in JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, and an LLM key
docker compose up --build
```

Open **http://localhost:8080** for the config UI — no CLI required to
connect Jira, choose an LLM provider, or schedule a recurring report.

Or drive it directly:
```bash
curl -X POST http://localhost:8000/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"connector": "jira", "board_id": "YOUR_PROJECT_KEY"}'
```

Want a fully local LLM with zero internet traffic?
```bash
# .env: LLM_PROVIDER=ollama
docker compose --profile ollama up --build
```

## Architecture
- FastAPI backend (`app/`) — connector, PII stripper, LLM provider, template renderer
- Celery worker + beat scheduler — fires scheduled reports on cron cadence
- Next.js config UI (`config-ui/`) — served on `:8080`, localhost-only
- Postgres for report/schedule/template metadata
- Redis for the job queue
- Chroma as the embedded vector DB
- PII stripping runs on every ticket before it reaches any LLM

## Deploying on Kubernetes

A basic Helm chart lives in `helm/reportapi/`:
```bash
helm install reportapi ./helm/reportapi --set envSecret.JIRA_API_TOKEN=... 
```
See `helm/reportapi/values.yaml` for the full set of overrides.

## Docs
- [Quickstart](docs/index.md)
- [Connector setup](docs/connector-setup.md)
- [LLM configuration](docs/llm-config.md)
- [Template guide](docs/template-guide.md)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## Licence
MIT — see [LICENSE](LICENSE). Community tier requires no license key. A
paid tier scaffold exists (`app/core/license_gate.py`) for future premium
features; nothing in the current feature set is gated.
