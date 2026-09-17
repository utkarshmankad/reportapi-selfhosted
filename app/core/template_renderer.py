"""Sandboxed Jinja2 rendering for report templates.

Templates are user-uploaded, so rendering uses jinja2's SandboxedEnvironment
(blocks access to unsafe attributes/methods) with no loader configured at all —
templates are rendered only from a string via `from_string`, so there is no
filesystem or OS access available to template authors.
"""

from datetime import datetime, timezone

from app.core.render_process import TemplateRenderError as TemplateRenderError
from app.core.render_process import run_render
from app.db.models import Report

DEFAULT_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Sprint Report</title>
<style>
  body { font-family: sans-serif; color: #1b1f24; max-width: 720px; margin: 40px auto; }
  h1 { font-size: 22px; border-bottom: 2px solid #0e8a76; padding-bottom: 8px; }
  .meta { color: #666e78; font-size: 12px; margin-bottom: 24px; }
  .narrative { font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
</style>
</head>
<body>
  <h1>Sprint Report — {{ report.connector | upper }}</h1>
  <div class="meta">
    Generated {{ report.created_at }} · {{ report.model_used }} · {{ report.tokens_used }} tokens
  </div>
  <div class="narrative">{{ report.narrative }}</div>
</body>
</html>
"""


def _build_context(report: Report) -> dict:
    return {
        "report": {
            "connector": report.connector,
            "status": report.status,
            "model_used": report.model_used,
            "tokens_used": report.tokens_used,
            "narrative": report.narrative,
            "created_at": report.created_at,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_template(content: str) -> None:
    run_render("validate", content)


def render_template(content: str, report: Report) -> str:
    return run_render("html", content, _build_context(report)).decode()


def render_report_pdf(content: str, report: Report) -> bytes:
    return run_render("report_pdf", content, _build_context(report))


def render_markdown(report: Report) -> str:
    return (
        f"# Sprint Report — {report.connector}\n\n"
        f"_Generated {report.created_at} · {report.model_used} · {report.tokens_used} tokens_\n\n"
        f"{report.narrative}\n"
    )
