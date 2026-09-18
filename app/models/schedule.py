"""Schedule request and response contracts."""

from datetime import datetime
from uuid import UUID

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.report import GenerateReportRequest


class CreateScheduleRequest(GenerateReportRequest):
    connector: str = "jira"
    cron_expression: str = Field(max_length=100)
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
            raise ValueError("Enter a valid five-field cron expression (UTC)")
        return value


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connector: str
    board_id: str | None
    sprint_id: str | None
    cron_expression: str
    output_format: str
    assigned_means_in_progress: bool
    period_start: datetime | None
    period_end: datetime | None
    active: bool
    last_run_at: datetime | None
    last_attempted_at: datetime | None
    created_at: datetime
