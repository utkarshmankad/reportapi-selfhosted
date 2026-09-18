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
- Experimental Helm skeleton; Compose is the supported deployment path

## Next steps

- [Connector setup](connector-setup.md)
- [LLM configuration](llm-config.md)
- [Template guide](template-guide.md)
