"""Schedule pydantic schema."""
from typing import Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class CreateScheduleRequest(BaseModel):
    connector: str = "jira"
    board_id: str | None = None
    sprint_id: str | None = None
    cron_expression: str
    output_format: Literal["text", "markdown", "pdf"] = "text"


class ScheduleResponse(BaseModel):
    id: UUID
    connector: str
    board_id: str | None
    sprint_id: str | None
    cron_expression: str
    output_format: str
    active: bool
    last_run_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
