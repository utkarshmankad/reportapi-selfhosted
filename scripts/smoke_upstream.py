"""Deterministic Jira/Ollama stand-in. Only used by the isolated smoke stack."""

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def respond(self, payload, status=200):
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path.startswith("/rest/api/3/search"):
            now = datetime.now(timezone.utc).isoformat()
            self.respond(
                {
                    "issues": [
                        {
                            "key": "DEMO-1",
                            "fields": {
                                "summary": "Ship the reporting workspace",
                                "description": "Synthetic test ticket",
                                "status": {"name": "Done"},
                                "assignee": None,
                                "labels": [],
                                "created": now,
                                "updated": now,
                            },
                        }
                    ]
                }
            )
        elif self.path in ("/rest/api/3/myself", "/api/tags"):
            self.respond({"models": []})
        else:
            self.respond({"detail": "Not found"}, 404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/chat":
            self.respond(
                {
                    "message": {"content": "1 ticket: done 1. Reporting workspace shipped."},
                    "prompt_eval_count": 10,
                    "eval_count": 10,
                }
            )
        else:
            self.respond({"detail": "Not found"}, 404)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
