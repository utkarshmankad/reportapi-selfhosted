"""Bounded subprocess execution for untrusted templates and PDF layout."""

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

MAX_TEMPLATE_BYTES = 50_000
MAX_INPUT_BYTES = 1_000_000
MAX_HTML_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 5_000_000
WALL_SECONDS = 15
CPU_SECONDS = 10
MEMORY_BYTES = 768 * 1024 * 1024
_slots = threading.BoundedSemaphore(2)


class TemplateRenderError(Exception):
    pass


def run_render(operation: str, content: str, context: dict | None = None) -> bytes:
    limit = MAX_HTML_BYTES if operation == "pdf" else MAX_TEMPLATE_BYTES
    if len(content.encode()) > limit:
        raise TemplateRenderError("Template or HTML exceeds the size limit")
    payload = json.dumps(
        {"operation": operation, "content": content, "context": context or {}}, default=str
    ).encode()
    if len(payload) > MAX_INPUT_BYTES + MAX_HTML_BYTES:
        raise TemplateRenderError("Report exceeds the input size limit")
    if context and len(json.dumps(context, default=str).encode()) > MAX_INPUT_BYTES:
        raise TemplateRenderError("Report exceeds the input size limit")
    if not _slots.acquire(blocking=False):
        raise TemplateRenderError("Renderer is busy; try again shortly")
    try:
        with tempfile.TemporaryDirectory(prefix="report-render-") as directory:
            output = Path(directory) / "output"
            try:
                result = subprocess.run(  # no shell; only the bundled worker is executable
                    [sys.executable, "-m", "app.core.render_worker", str(output)],
                    input=payload,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=WALL_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise TemplateRenderError("Rendering exceeded the time limit") from None
            if result.returncode or not output.exists():
                raise TemplateRenderError("Invalid template or rendering resource limit exceeded")
            with output.open("rb") as rendered:
                data = rendered.read(MAX_OUTPUT_BYTES + 1)
            if len(data) > MAX_OUTPUT_BYTES:
                raise TemplateRenderError("Rendered output exceeds the size limit")
            return data
    finally:
        _slots.release()
