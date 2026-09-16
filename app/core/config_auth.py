"""Auth guard for the privileged /api/config/* routes.

These endpoints save credentials and act as an SSRF-test oracle, so they
should never be reachable by an untrusted caller. If CONFIG_API_TOKEN is
set, callers must send it as X-Config-Token. It's unset by default for
local dev; set it whenever the api port might be reachable from anywhere
other than your own machine.
"""

from secrets import compare_digest

from fastapi import Header, HTTPException

from app.config import settings


async def require_config_token(x_config_token: str | None = Header(default=None)) -> None:
    if not settings.config_api_token:
        return
    if not x_config_token or not compare_digest(x_config_token, settings.config_api_token):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Config-Token")
