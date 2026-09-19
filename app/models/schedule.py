"""Schedule request and response contracts."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.report import GenerateReportRequest


class CreateScheduleRequest(GenerateReportRequest):
    connector: str = "jira"
    cron_expression: str = Field(max_length=100)
    # An IANA zone name — "UTC", "America/New_York", "Europe/London", etc.
    # Cron fields are wall-clock time in this zone; see docs/scheduling.md
    # for exactly what that means across a DST transition.
    timezone: str = Field(default="UTC", max_length=64)
    active: bool = True

    @field_validator("connector")
    @classmethod
    def known_connector(cls, value):
        if value not in {"jira", "asana", "github"}:
            raise ValueError("Unsupported connector")
        return value

    @field_validator("cron_expression")
    @classmethod
    def valid_cron(cls, value):
        if len(value.split()) != 5 or not croniter.is_valid(value):
            raise ValueError("Enter a valid five-field cron expression")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(f"'{value}' is not a recognized IANA timezone name") from None
        return value


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connector: str
    board_id: str | None
    sprint_id: str | None
    cron_expression: str
    timezone: str
    output_format: str
    assigned_means_in_progress: bool
    period_start: datetime | None
    period_end: datetime | None
    active: bool
    last_run_at: datetime | None
    last_attempted_at: datetime | None
    created_at: datetime


class NextRunsResponse(BaseModel):
    # Explicit UTC timestamps, not local wall-clock strings, so the caller
    # never has to re-derive what "9am local" meant at a given instant —
    # each entry here already answers that.
    next_runs_utc: list[datetime]
