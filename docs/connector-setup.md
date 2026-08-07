# Connector setup

v0.5.1 ships two connectors: **Jira Cloud** and **Asana**. More connectors
(GitHub Issues, Linear, Trello) are tracked on the roadmap, not yet built.

## Jira

### Getting a Jira API token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create an API token, copy it immediately — Atlassian won't show it again.

### Configure via the browser

Open the config UI (`http://localhost:8080`), go to the **Jira** section,
and fill in:

| Field | Example |
|---|---|
| Jira URL | `https://yourcompany.atlassian.net` |
| Email | `you@company.com` |
| API token | (the token from above) |

Click **Test connection** before saving — it calls `/rest/api/3/myself` to
confirm the credentials work.

### Configure via `.env`

```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_token_here
```

### What gets fetched

Given a `board_id` (project key) or `sprint_id`, the connector pulls issues
via JQL and normalises them into the shared `Ticket` shape: title,
description, status (`todo`/`in_progress`/`done`/`blocked`), assignee,
priority, labels, sprint, and URL. Jira's Atlassian Document Format
descriptions are flattened to plain text before anything downstream sees
them.

## Asana

Asana is aimed at solo developers and small teams who use it instead of a
heavier tool like Jira — status updates, client reports, and changelogs
generated straight from an Asana project.

### Getting an Asana Personal Access Token

1. Go to your [Asana developer console](https://app.asana.com/0/my-apps)
2. Create a **Personal Access Token**, copy it immediately.

Unlike Jira, Asana needs only the one token — no separate email/URL pair.

### Configure via the browser

Open the config UI, go to the **Asana** section, and paste the token.
Click **Test connection** — it calls `/api/1.0/users/me` to confirm the
token works.

### Configure via `.env`

```bash
ASANA_PAT=your_personal_access_token_here
```

### `board_id` / `sprint_id` mapping

Asana has no native board/sprint split — work lives in **projects**,
optionally grouped into **sections**. The connector reuses the same request
shape as Jira so the rest of the API (schedules, templates) doesn't need a
per-connector branch:

| Request field | Asana concept | Where to find the GID |
|---|---|---|
| `board_id` | Project GID | Project URL: `app.asana.com/0/`**`<project_gid>`**`/list` |
| `sprint_id` | Section GID (optional, narrows to one section within a project) | Right-click a section header → Copy section URL |

```bash
curl -X POST http://localhost:8000/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"connector": "asana", "board_id": "1201234567890"}'
```

### What gets fetched

Tasks are normalised into the same `Ticket` shape used by Jira:

- **status** — Asana tasks only have a `completed` boolean natively. The
  connector first checks which section a task sits in (`To Do` / `In
  Progress` / `Blocked` / `Done`-style names are recognised) and falls back
  to `done`/`todo` from the `completed` flag if the section name isn't
  recognised.
- **priority** — Asana has no built-in priority field. If your project has
  a custom field literally named `Priority`, its value is used; otherwise
  priority is left blank.
- **labels** — Asana tags.
- **sprint** — the task's current section name, shown as-is (e.g. `Sprint
  3`, `This Week`, whatever your project calls its sections).

## PII stripping

Ticket title and description are stripped of PII (emails, phone numbers,
national ID formats, card numbers) before they're sent to any LLM,
regardless of connector — see [llm-config.md](llm-config.md).
