"""Render PDFs without fetching template-controlled files or network URLs."""

from weasyprint import HTML


def deny_resource(url, *args, **kwargs):
    raise ValueError("External PDF resources are disabled")


def render_pdf(html: str) -> bytes:
    return HTML(string=html, url_fetcher=deny_resource).write_pdf()
