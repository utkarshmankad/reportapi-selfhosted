# Security and configuration boundaries

## Instance access

`APP_ENV=production` requires a nonblank `CONFIG_API_TOKEN`; API, worker and beat
refuse to start without it. All `/api/*` routes require `X-Config-Token` when
configured. `/health` is public. `APP_ENV=development` without a token is only for
local development. Compose binds the API and UI to loopback by default. Use a
TLS reverse proxy and a token when publishing them. The UI keeps the token in
page memory, not browser storage or build assets.

## Privacy contract

Filtering is mandatory for every connector/provider before report generation:

- Email addresses matching the supported ASCII pattern.
- PAN, contiguous 12-digit Aadhaar patterns, and 10-digit Indian mobile patterns.
- Luhn-valid 13–19-digit cards, including single-space and hyphen separators;
  replacements use original text spans.
- Valid dotted IPv4 and colon-form IPv6 literals, including IPv4-mapped and scoped IPv6.
- Assignees become `Person 1`, `Person 2`, etc. consistently within a report.
  Exact known assignee names are replaced case-insensitively in ticket text.
  The temporary alias map is not persisted. Names are collected across the entire
  report before filtering, so another ticket's assignee is recognized too.
- All textual ticket fields used by prompt construction, including priority and
  status, are filtered; the assembled outbound user prompt is filtered again.

This is **pattern filtering and pseudonymization, not complete anonymization**.
Unknown names, nicknames, addresses, unusual/obfuscated identifier formats, and
contextual identity clues may remain. Matching can also over-redact unrelated
numbers or words. Aliases do not identify the same person across different
reports. Existing stored reports are not retroactively rewritten. A model may
invent sensitive-looking output; review reports before sharing them.

Cloud providers receive the filtered prompt. Local Ollama avoids external LLM
requests only when the operator configures a local server. Ticket connectors
still contact their upstream services, and initial model/image downloads need
network access. This software does not guarantee regulatory compliance.

## Outbound destinations

Configure these **operator-only** environment values on API, worker and beat:

```dotenv
JIRA_ALLOWED_ORIGINS=https://yourcompany.atlassian.net
OLLAMA_ALLOWED_ORIGINS=http://ollama:11434
OUTBOUND_PRIVATE_ORIGINS=http://ollama:11434
```

Each value is a comma-separated list of exact origins (scheme, hostname, port).
Jira's default list is empty: set it before saving/testing/using Jira. Changing a
URL in the UI never authorizes a new destination. A custom internal service must
appear in its service allowlist **and** `OUTBOUND_PRIVATE_ORIGINS`. The default
Ollama entries deliberately permit the Compose service on its private network.
Loopback, link-local, metadata, multicast, reserved and unspecified addresses
remain blocked even if listed. Use a container/service hostname for local Ollama.

The same origin policy applies to save, test and runtime Jira/Ollama requests.
Save/test resolve and validate the destination. Each actual connection resolves
again, checks every returned address, then connects to a checked numeric IP.
The original hostname remains the HTTP Host and TLS verification/SNI name.
Redirects and environment-proxy routing are disabled for these clients; response
bodies are limited to 10 MiB. Fixed Asana/GitHub/cloud-LLM endpoints are not
operator-selectable. Network retries/pagination remain later-sprint work.

## Durable configuration

Startup settings come from environment variables over `.env` over defaults.
When `CONFIG_READ_ONLY=false`, allowlisted values in `CONFIG_STORE_PATH` override
startup connector/provider settings for new reports. Compose stores that file at
`/config/runtime.env` in a named volume shared by API, worker and beat. Every job
reads one complete file snapshot before any external request; in-flight jobs
retain their provider, credentials and output settings. Removing an override
restores the startup value on the next read. Changing startup settings requires
service recreation.

Writes use a process lock, a same-directory temporary file, quoted literal values,
owner-only permissions, file/directory synchronization, and atomic replacement.
Concurrent saves retain unrelated keys. Replacing an existing permissive file
repairs it to mode `0600`. The runtime file contains plaintext secrets: protect
its volume and backups. Do not make the configuration directory writable by
untrusted users. All processes sharing it must have compatible filesystem ownership.

For external secret management, set `CONFIG_READ_ONLY=true`. Runtime overrides
are ignored; API saves fail and the UI identifies operator-managed connections.
Config status exposes configured flags, provider, non-secret URL and management
mode, never credential values. A configured flag means present, not a successful
connection test. No credentials, token, database URL, or destination allowlist can
be read or overwritten through arbitrary config keys.

## Template/PDF limits

Template parsing, Jinja evaluation and WeasyPrint layout run in a separate process:

| Limit | Value |
|---|---:|
| Template UTF-8 bytes | 50,000 |
| Serialized report context bytes | 1,000,000 |
| Rendered HTML bytes | 2,000,000 |
| Output file bytes | 5,000,000 |
| Wall time per operation | 15 seconds |
| CPU time per worker | 10 seconds |
| Address space per worker (Linux) | 768 MiB |
| Concurrent workers per API process | 2 |

The Jinja sandbox has no template loader and autoescapes report fields. The PDF
URL fetcher denies **all** external resources: file, HTTP(S), CSS imports, fonts,
and data URLs. Inline CSS and ordinary markup work; linked/embedded image assets
are not supported. Resource references are not fetched (WeasyPrint may omit them
and still produce a PDF). Limits or invalid templates return a generic `422`;
retry busy responses later. The API event loop does not execute rendering work.

Linux containers are the supported boundary for untrusted templates. Native
macOS development has time/output limits but no reliable address-space limit.
This is resource isolation plus language/fetcher restrictions, not an OS security
sandbox. Keep rendering dependencies patched and restrict who has instance access.

The design follows the resource-isolation advice in the
[Jinja sandbox documentation](https://jinja.palletsprojects.com/en/stable/sandbox/)
and [WeasyPrint security guidance](https://doc.courtbouillon.org/weasyprint/latest/first_steps.html).
