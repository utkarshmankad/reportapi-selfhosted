# Connector setup — Jira

v0.5 ships one connector: Jira Cloud. More connectors (Linear, GitHub Issues,
Azure DevOps) are tracked on the roadmap, not yet built.

## Getting a Jira API token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create an API token, copy it immediately — Atlassian won't show it again.

## Configure via the browser

Open the config UI (`http://localhost:8080`), go to the **Jira** section,
and fill in:

| Field | Example |
|---|---|
| Jira URL | `https://yourcompany.atlassian.net` |
| Email | `you@company.com` |
| API token | (the token from above) |

Click **Test connection** before saving — it calls `/rest/api/3/myself` to
confirm the credentials work.

## Configure via `.env`

```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_token_here
```

Restart the `api` and `worker` containers after editing `.env` directly —
`Settings` is loaded once at process startup.

## What gets fetched

Given a `board_id` (project key) or `sprint_id`, the connector pulls issues
via JQL and normalises them into the shared `Ticket` shape: title,
description, status (`todo`/`in_progress`/`done`/`blocked`), assignee,
priority, labels, sprint, and URL. Jira's Atlassian Document Format
descriptions are flattened to plain text before anything downstream sees
them.

Ticket title and description are stripped of PII (emails, phone numbers,
national ID formats, card numbers) before they're sent to any LLM — see
[llm-config.md](llm-config.md).
