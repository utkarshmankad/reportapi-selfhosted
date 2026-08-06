# ReportAPI Self-Hosted

Container-native reporting engine for Agile ticket data. Runs entirely on
your own infrastructure — no data leaves your network, and PII is stripped
before any ticket content reaches an LLM.

## Quickstart

```bash
git clone https://github.com/utkarshmankad/reportapi-selfhosted.git
cd reportapi-selfhosted
cp .env.example .env
# fill in JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, OPENAI_API_KEY
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
- Helm chart for Kubernetes deployments

## Next steps

- [Connector setup](connector-setup.md)
- [LLM configuration](llm-config.md)
- [Template guide](template-guide.md)
