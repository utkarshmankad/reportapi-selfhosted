"""Report profile pydantic schema."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.report import validate_connector_scope


class CreateReportProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    connector: Literal["jira", "asana", "github"]
    board_id: str | None = Field(default=None, max_length=100)
    sprint_id: str | None = Field(default=None, max_length=100)
    output_format: Literal["text", "markdown", "pdf"] = "text"
    template_id: UUID | None = None
    assigned_means_in_progress: bool = True

    @model_validator(mode="after")
    def validate_scope(self):
        self.board_id = (self.board_id or "").strip() or None
        self.sprint_id = (self.sprint_id or "").strip() or None
        validate_connector_scope(self.connector, self.board_id, self.sprint_id)
        return self


class UpdateReportProfileRequest(BaseModel):
    """All fields optional — an update only touches what's provided."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    connector: Literal["jira", "asana", "github"] | None = None
    board_id: str | None = Field(default=None, max_length=100)
    sprint_id: str | None = Field(default=None, max_length=100)
    output_format: Literal["text", "markdown", "pdf"] | None = None
    template_id: UUID | None = None
    assigned_means_in_progress: bool | None = None


class ReportProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    connector: str
    board_id: str | None
    sprint_id: str | None
    output_format: str
    assigned_means_in_progress: bool
    template_id: UUID | None
    created_at: datetime
    updated_at: datetime


class GenerateFromProfileRequest(BaseModel):
    """Optional per-run overrides — a profile's stored scope/format is the
    default, but the reporting period is deliberately never stored on the
    profile itself (it would go stale the moment a fixed range is saved),
    so it's supplied fresh on every generate call instead."""

    period_start: datetime | None = None
    period_end: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self
