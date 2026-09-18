"""Private worker entry point. Limits apply before importing either rendering engine."""

import json
import resource
import sys

from app.core.render_process import CPU_SECONDS, MAX_HTML_BYTES, MAX_OUTPUT_BYTES, MEMORY_BYTES


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    # RLIMIT_AS is enforced on Linux (the supported container deployment).
    # macOS does not reliably implement address-space limits; use containers for untrusted input.
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    from jinja2.sandbox import SandboxedEnvironment

    payload = json.load(sys.stdin)
    operation = payload["operation"]
    content = payload["content"]
    if operation != "pdf":
        template = SandboxedEnvironment(autoescape=True).from_string(content)
        if operation == "validate":
            content = ""
        else:
            parts = []
            size = 0
            for part in template.generate(**payload["context"]):
                size += len(part.encode())
                if size > MAX_HTML_BYTES:
                    raise ValueError("HTML output too large")
                parts.append(part)
            content = "".join(parts)
    with open(sys.argv[1], "wb") as output:
        if operation in ("pdf", "report_pdf"):
            from weasyprint import HTML

            from app.core.pdf_renderer import deny_resource

            HTML(string=content, url_fetcher=deny_resource).write_pdf(output)
        else:
            output.write(content.encode())


if __name__ == "__main__":
    main()
