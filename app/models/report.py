"""Report pydantic schema."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerateReportRequest(BaseModel):
    connector: Literal["jira", "asana", "github"]
    board_id: str | None = Field(default=None, max_length=100)
    sprint_id: str | None = Field(default=None, max_length=100)
    output_format: Literal["text", "markdown", "pdf"] = "text"
    template_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        self.board_id = (self.board_id or "").strip() or None
        self.sprint_id = (self.sprint_id or "").strip() or None
        if not self.board_id and not self.sprint_id:
            raise ValueError("Either board_id or sprint_id is required")
        if self.connector == "github" and (not self.board_id or len(self.board_id.split("/")) != 2):
            raise ValueError("GitHub requires a repository in owner/repo format")
        return self


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connector: str
    status: str
    narrative: str | None
    tokens_used: int
    model_used: str
    output_format: str
    created_at: datetime


class GenerateReportResponse(BaseModel):
    report_id: UUID
    status: str
    narrative: str
    tokens_used: int
    model_used: str
    ticket_count: int
    output_format: str
