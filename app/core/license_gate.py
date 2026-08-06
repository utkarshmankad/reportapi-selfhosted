"""License gate scaffold.

Community tier ships with every v0.1–v0.5 feature and requires no key at all.
This module exists so a future paid tier (extra connectors, hosted scheduling,
etc.) has a single, consistent place to gate on — nothing in the codebase
calls `require_paid_tier` yet.
"""
from fastapi import HTTPException
from app.config import settings


def is_licensed() -> bool:
    if settings.license_tier == "community":
        return True
    return bool(settings.license_key) and _validate_key_format(settings.license_key)


def _validate_key_format(key: str) -> bool:
    # Placeholder shape check only — no license server exists yet.
    # A real implementation would verify a signature or call a licensing API.
    return key.startswith("reportapi_") and len(key) >= 20


async def require_paid_tier() -> None:
    """FastAPI dependency for routes that should be paid-tier-only."""
    if not is_licensed():
        raise HTTPException(
            status_code=402,
            detail="This feature requires a paid ReportAPI license. "
                   "Set LICENSE_TIER=paid and LICENSE_KEY in your environment.",
        )
