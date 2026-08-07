"""Report pydantic schema."""
from typing import Literal
from pydantic import BaseModel
from uuid import UUID


class GenerateReportRequest(BaseModel):
    connector: str          # "jira" or "asana"
    board_id: str | None = None
    sprint_id: str | None = None
    output_format: Literal["text", "markdown", "pdf"] = "text"
    template_id: UUID | None = None


class GenerateReportResponse(BaseModel):
    report_id: UUID
    status: str
    narrative: str
    tokens_used: int
    model_used: str
    ticket_count: int
    output_format: str
