"""Export the FastAPI OpenAPI schema for frontend type generation.

Run from the repo root: poetry run python scripts/export_openapi.py
Writes config-ui/openapi.json, which `npm run generate:types` turns into
TypeScript types (config-ui/lib/api-types.generated.ts) — the single
source of truth for both sides instead of two hand-maintained copies
that can silently drift apart.
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "config-ui" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
