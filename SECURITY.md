# Security Policy

ReportAPI Self-Hosted processes ticket data that may contain personal
information before it reaches a third-party LLM. We take reports of security
issues seriously.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x   | ✅ |
| < 0.5   | ❌ (pre-release, upgrade instead) |

## Reporting a vulnerability

**Do not open a public GitHub issue.** Instead, email
**security@reportapi.dev** (or the maintainer's address listed in the repo)
with:

- A description of the vulnerability and its impact
- Steps to reproduce, or a proof of concept
- The version/commit you tested against

We aim to acknowledge reports within 5 business days and to ship a fix or
mitigation within 30 days for confirmed issues, depending on severity.

## Scope

Particular attention areas for this project:

- **PII stripping** (`app/core/pii.py`) — any regex or bypass that lets
  personal data reach an LLM provider unredacted.
- **Template sandboxing** (`app/core/template_renderer.py`) — any way for an
  uploaded Jinja2 template to reach the filesystem, environment, or OS.
- **Credential handling** — API tokens (Jira, OpenAI, Anthropic) leaking into
  logs, error messages, or the config UI's stored `.env`.
- **License gate** (`app/core/license_gate.py`) — bypasses that shouldn't be
  treated as a security bug (the Community tier is meant to be free and
  ungated) but architectural issues are still welcome as regular issues.

Thank you for helping keep self-hosted deployments of this project safe.
