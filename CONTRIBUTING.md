# Contributing to ReportAPI Self-Hosted

Thanks for considering a contribution. This project is young — expect the
internals to move fast between minor versions.

## Development setup

```bash
git clone https://github.com/utkarshmankad/reportapi-selfhosted.git
cd reportapi-selfhosted
poetry install
cp .env.example .env
docker compose up --build
```

Run tests before opening a PR:

```bash
poetry run pytest
```

## Ground rules

- **Connectors** implement `app.connectors.base.Connector`. New connectors live
  in `app/connectors/`, alongside a normaliser into the shared `Ticket` model.
- **LLM providers** implement `app.llm.base.LLMProvider`. Keep provider-specific
  auth and request shaping inside the provider — the factory should stay a
  simple router on `LLM_PROVIDER`.
- **PII stripping is not optional.** Any code path that sends ticket content to
  an LLM or a template must run it through `app.core.pii.strip_pii_from_ticket`
  first. PRs that bypass this will be rejected.
- **Templates render sandboxed.** Anything touching `app.core.template_renderer`
  must keep the `SandboxedEnvironment` with no filesystem loader — user-supplied
  templates should never gain OS or filesystem access.

## Pull requests

1. Fork, branch off `main`, keep changes scoped to one concern.
2. Add or update tests for anything you change — `poetry run pytest -v` must
   pass clean.
3. Describe *why* in the PR description, not just what changed.
4. Small PRs get reviewed faster than large ones.

## Reporting bugs

Open a GitHub issue with: what you ran, what you expected, what you got, and
your `LLM_PROVIDER` / connector combination. Logs help — redact any tokens
first.

## Security issues

Do not open a public issue for a security vulnerability. See [SECURITY.md](SECURITY.md).
