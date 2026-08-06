"""Sandboxed Jinja2 rendering for report templates.

Templates are user-uploaded, so rendering uses jinja2's SandboxedEnvironment
(blocks access to unsafe attributes/methods) with no loader configured at all —
templates are rendered only from a string via `from_string`, so there is no
filesystem or OS access available to template authors.
"""
from datetime import datetime, timezone
from jinja2.sandbox import SandboxedEnvironment
from jinja2.exceptions import TemplateError
from app.db.models import Report

_env = SandboxedEnvironment(autoescape=True)

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


class TemplateRenderError(Exception):
    pass


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
    """Raise TemplateRenderError if the template has a syntax error."""
    try:
        _env.from_string(content)
    except TemplateError as e:
        raise TemplateRenderError(f"Invalid template: {str(e)}")


def render_template(content: str, report: Report) -> str:
    try:
        template = _env.from_string(content)
        return template.render(**_build_context(report))
    except TemplateError as e:
        raise TemplateRenderError(f"Template rendering failed: {str(e)}")


def render_markdown(report: Report) -> str:
    return (
        f"# Sprint Report — {report.connector}\n\n"
        f"_Generated {report.created_at} · {report.model_used} · {report.tokens_used} tokens_\n\n"
        f"{report.narrative}\n"
    )
