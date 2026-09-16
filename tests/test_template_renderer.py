import uuid
from datetime import datetime, timezone

import pytest

from app.core.pdf_renderer import render_pdf
from app.core.template_renderer import (
    DEFAULT_TEMPLATE,
    TemplateRenderError,
    render_markdown,
    render_template,
    validate_template,
)
from app.db.models import Report


def make_report():
    return Report(
        id=uuid.uuid4(),
        connector="jira",
        status="complete",
        model_used="openai",
        tokens_used=123,
        narrative="Everything shipped on time.",
        output_format="pdf",
        created_at=datetime.now(timezone.utc),
    )


def test_validate_template_rejects_bad_syntax():
    with pytest.raises(TemplateRenderError):
        validate_template("{{ unterminated")


def test_validate_template_accepts_default():
    validate_template(DEFAULT_TEMPLATE)


def test_render_template_includes_narrative():
    html = render_template(DEFAULT_TEMPLATE, make_report())
    assert "Everything shipped on time." in html


def test_template_cannot_reach_filesystem():
    # Sandboxed env with no loader configured — os/import are not in scope.
    malicious = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    with pytest.raises(TemplateRenderError):
        render_template(malicious, make_report())


def test_render_markdown_includes_narrative():
    md = render_markdown(make_report())
    assert "Everything shipped on time." in md
    assert md.startswith("# Sprint Report")


def test_render_pdf_produces_bytes():
    pdf = render_pdf("<html><body><h1>Test</h1></body></html>")
    assert pdf[:4] == b"%PDF"
