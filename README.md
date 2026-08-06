# ReportAPI Self-Hosted

Container-native reporting engine for Agile ticket data. Runs entirely
on your own infrastructure — no data leaves your network.

## Status
v0.1 — Proof of concept. Jira connector + OpenAI provider only.

## Quick start

```bash
cp .env.example .env
# Fill in JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, OPENAI_API_KEY
docker compose up --build
```

Test:
```bash
curl -X POST http://localhost:8000/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"connector": "jira", "board_id": "YOUR_PROJECT_KEY"}'
```

## Architecture
- FastAPI backend (`app/`)
- Celery worker for scheduled jobs (not yet wired up in v0.1)
- Postgres for report metadata
- Redis for job queue
- PII stripping runs on every ticket before it reaches any LLM

## Roadmap
See the ReportAPI Self-Hosted roadmap in the project's Notion workspace.

## Licence
TBD — MIT or Apache 2.0 at v0.5 Community launch.
