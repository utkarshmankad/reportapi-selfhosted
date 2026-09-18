# Template guide

Generate a narrative first, then request `/api/report/<id>/render?format=pdf`.
The generation response remains JSON even when `output_format` is `pdf`. Upload
a custom template to change the export layout.

## Uploading a template

```bash
curl -X POST http://localhost:8000/api/templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Weekly",
    "content": "<html>...your Jinja2 markup...</html>"
  }'
```

The response includes an `id` — you don't reference it at generation
time. Instead, request a specific rendering of an existing report:

```bash
curl "http://localhost:8000/api/report/<report_id>/render?format=pdf&template_id=<template_id>" \
  --output report.pdf
```

## What's available in a template

Templates render with a `report` object in scope:

```jinja
{{ report.connector }}      {# "jira" #}
{{ report.model_used }}     {# "openai" #}
{{ report.tokens_used }}    {# 245 #}
{{ report.narrative }}      {# the generated text #}
{{ report.created_at }}
```

Plus `generated_at`, an ISO timestamp of the current render.

## Sandboxing

Templates render inside a Jinja2 `SandboxedEnvironment` with **no filesystem
loader configured at all** — templates are rendered only from the string you
uploaded via `from_string()`. There's no `{% include %}`, no `{% import %}`
from disk, and the sandbox blocks the usual attribute-escape tricks (reaching
a class's `__mro__`, etc.).

If your template has a syntax error, `/api/templates` returns `422` at
upload time — you don't find out at render time in front of a stakeholder.

## Output formats

| `output_format` | What you get |
|---|---|
| `text` | Raw narrative, no formatting |
| `markdown` | Narrative wrapped in a `# Sprint Report` heading + metadata line |
| `pdf` | Rendered through your template (or the default) via WeasyPrint |

## Resource restrictions

Parsing and rendering run in a bounded subprocess: 50 KB template, 1 MB context,
2 MB HTML, 5 MB output, 15-second wall time, 10-second CPU time, and 768 MiB
address space on Linux. At most two workers run per API process. File, network,
and data-URL resources are denied, including CSS imports and linked fonts/images.
Use inline styles. See [full limits and platform scope](security-boundaries.md#templatepdf-limits).

When instance authentication is enabled, add `-H "X-Config-Token: $CONFIG_API_TOKEN"`
to the examples above.
