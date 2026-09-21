# ReportAPI Self-Hosted

Container-native reporting engine for Agile ticket data. Runs entirely on
your own infrastructure. Cloud LLM providers receive filtered prompts; local Ollama keeps inference local. [Supported identifier filtering](security-boundaries.md#privacy-contract) is mandatory, but is not complete anonymization.

## Quickstart

```bash
git clone https://github.com/utkarshmankad/reportapi-selfhosted.git
cd reportapi-selfhosted
cp .env.example .env
# fill in JIRA_URL, JIRA_ALLOWED_ORIGINS, JIRA_EMAIL, JIRA_API_TOKEN, OPENAI_API_KEY
# for production: APP_ENV=production and a strong CONFIG_API_TOKEN
docker compose up --build
```

Open the config UI at [http://localhost:8080](http://localhost:8080) and
walk through the Jira, LLM, and schedule forms — no `curl` required.

Or generate a report directly:

```bash
curl -X POST http://localhost:8000/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"connector": "jira", "board_id": "YOUR_PROJECT_KEY"}'
```

## What's in v0.5

- Jira connector, pluggable LLM (OpenAI / Anthropic / Ollama)
- PII stripping on every ticket before it reaches an LLM
- Scheduled reports via Celery beat
- PDF / Markdown / text output with sandboxed custom templates
- Browser-based config UI
- Named report profiles for repeatable on-demand generation
- Functional Helm chart (`helm/reportapi`) alongside the Compose deployment path

## Report profiles

A profile is a saved, named bundle of manual-generate parameters
(connector, board/sprint, template, output format) — the on-demand
equivalent of a Schedule, which exists for recurring generation
instead. Generating from a profile never creates or touches a
Schedule.

```bash
curl -X POST http://localhost:8000/api/report-profiles \
  -H "X-Config-Token: $CONFIG_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Weekly demo", "connector": "jira", "board_id": "DEMO"}'

curl -X POST http://localhost:8000/api/report-profiles/<id>/generate \
  -H "X-Config-Token: $CONFIG_API_TOKEN" -H "Content-Type: application/json" -d '{}'
```

The reporting period is deliberately not stored on the profile — it's
supplied fresh on each generate call (optional `period_start`/
`period_end`) so a saved profile never goes stale against a fixed date
range.

## Next steps

- [Connector setup](connector-setup.md)
- [LLM configuration](llm-config.md)
- [Template guide](template-guide.md)
- [Scheduling: timezones, DST, and missed runs](scheduling.md)
- [Operations runbook](runbook.md)
- [Reproducible builds](reproducible-builds.md)
- [Backup and restore](backup-restore.md)
- [Release-candidate checklist](release-checklist.md)
