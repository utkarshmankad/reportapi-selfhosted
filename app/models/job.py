"""Report job pydantic schema."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.report import GenerateReportRequest

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")


class CreateReportJobRequest(GenerateReportRequest):
    # Client-supplied dedup token: retrying the same logical request with
    # the same key returns the existing job instead of creating a
    # duplicate. Restricted to a safe, printable charset — this is stored
    # and matched verbatim, never interpreted.
    idempotency_key: str | None = Field(default=None)

    @field_validator("idempotency_key")
    @classmethod
    def valid_idempotency_key(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            return None
        if not _IDEMPOTENCY_KEY.match(value):
            raise ValueError(
                "idempotency_key must be 1-255 characters of letters, digits, '_', '.', ':' or '-'"
            )
        return value


class ReportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    connector: str
    board_id: str | None
    sprint_id: str | None
    output_format: str
    template_id: UUID | None
    report_id: UUID | None
    error_reason: str | None
    attempts: int
    schedule_id: UUID | None
    scheduled_for: datetime | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
