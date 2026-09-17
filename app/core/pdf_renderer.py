"""Render PDFs without fetching template-controlled files or network URLs."""

from app.core.render_process import run_render


def deny_resource(url, *args, **kwargs):
    raise ValueError("External PDF resources are disabled")


def render_pdf(html: str) -> bytes:
    return run_render("pdf", html)
