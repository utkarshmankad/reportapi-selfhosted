"""Renders HTML narratives to PDF via WeasyPrint."""
from weasyprint import HTML


def render_pdf(html: str) -> bytes:
    return HTML(string=html).write_pdf()
