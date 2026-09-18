# Connector setup

v0.5.2 ships three connectors: **Jira Cloud**, **Asana**, and **GitHub
Issues**. More connectors (Linear, Trello) are tracked on the roadmap, not
yet built.

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

## GitHub Issues

The lowest-friction connector for most developers: if you already host code
on GitHub, there's no new account or tool to adopt — just a token. Good fit
for changelog/release-note reports and OSS maintainer status updates.

### Getting a GitHub token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   and create a **fine-grained personal access token** (or a classic token
   with the `repo` scope for private repos; public-repo-only use needs no
   scopes).
2. Scope it to the repo(s) you want reported on, copy it immediately.

### Configure via the browser

Open the config UI, go to the **GitHub Issues** section, and paste the
token. Click **Test connection** — it calls `/user` to confirm the token
works.

### Configure via `.env`

```bash
GITHUB_PAT=your_personal_access_token_here
```

### `board_id` / `sprint_id` mapping

GitHub has no native board/sprint split either — issues live in a
**repo**, optionally grouped into a **milestone**:

| Request field | GitHub concept | Format |
|---|---|---|
| `board_id` | Repository | `owner/repo`, e.g. `octocat/hello-world` |
| `sprint_id` | Milestone number (optional, narrows to one milestone) | The number shown in the milestone's URL, e.g. `3` |

```bash
curl -X POST http://localhost:8000/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"connector": "github", "board_id": "octocat/hello-world"}'
```

### What gets fetched

Issues are normalised into the same `Ticket` shape used by Jira/Asana.
Pull requests are excluded automatically (GitHub's issues API returns both).

- **status** — GitHub issues only have `open`/`closed` natively. The
  connector checks labels first (`in progress`, `wip`, `blocked`, `on
  hold`-style names are recognised) and falls back to `done`/`todo` from
  the open/closed state.
- **priority** — GitHub has no built-in priority field. If an issue has a
  label starting with `priority:`, `priority/`, or matching `p0`–`p3`, that
  label is used as the priority; otherwise priority is left blank.
- **labels** — GitHub labels, as-is.
- **sprint** — the issue's milestone title, if any.

## Privacy and approved destinations

Set `JIRA_ALLOWED_ORIGINS` to your exact Jira origin before saving or using it.
The UI cannot authorize new destinations. See [outbound policy](security-boundaries.md#outbound-destinations).

All outbound ticket fields use mandatory supported-identifier filtering and
report-local assignee aliases. Unknown names and contextual clues may remain;
see [precise privacy coverage](security-boundaries.md#privacy-contract).
