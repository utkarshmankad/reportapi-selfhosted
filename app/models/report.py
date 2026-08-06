"""Report pydantic schema."""
from pydantic import BaseModel
from uuid import UUID


class GenerateReportRequest(BaseModel):
    connector: str          # "jira" only in v0.1
    board_id: str | None = None
    sprint_id: str | None = None


class GenerateReportResponse(BaseModel):
    report_id: UUID
    status: str
    narrative: str
    tokens_used: int
    model_used: str
    ticket_count: int
