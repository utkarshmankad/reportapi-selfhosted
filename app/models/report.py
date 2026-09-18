"""Report pydantic schema."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Connector-specific identifier shapes. These are deliberately strict
# allowlists: they double as injection defenses for Jira JQL (built from
# board_id/sprint_id via string interpolation) and for GitHub/Asana URL
# path segments, not just format hints.
_JIRA_PROJECT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,9}$")
_JIRA_SPRINT_ID = re.compile(r"^[0-9]{1,10}$")
_ASANA_GID = re.compile(r"^[0-9]{1,19}$")
_GITHUB_REPO_SEGMENT = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})"
_GITHUB_REPO = re.compile(rf"^{_GITHUB_REPO_SEGMENT}/{_GITHUB_REPO_SEGMENT}$")
_GITHUB_MILESTONE = re.compile(r"^[0-9]{1,10}$")

_CONNECTOR_SCOPE_RULES: dict[str, dict[str, re.Pattern]] = {
    "jira": {"board_id": _JIRA_PROJECT_KEY, "sprint_id": _JIRA_SPRINT_ID},
    "asana": {"board_id": _ASANA_GID, "sprint_id": _ASANA_GID},
    "github": {"board_id": _GITHUB_REPO, "sprint_id": _GITHUB_MILESTONE},
}


def validate_connector_scope(connector: str, board_id: str | None, sprint_id: str | None) -> None:
    """Enforce the typed identifier shape for a connector's board_id/sprint_id.

    Shared by manual report requests and schedules so both paths reject the
    same malformed or injection-shaped identifiers before any outbound call.
    """
    if not board_id and not sprint_id:
        raise ValueError("Either board_id or sprint_id is required")

    rules = _CONNECTOR_SCOPE_RULES.get(connector)
    if rules is None:
        raise ValueError(f"Unsupported connector: {connector}")

    if connector == "github" and not board_id:
        raise ValueError("GitHub requires a repository in owner/repo format")

    if board_id is not None and not rules["board_id"].match(board_id):
        raise ValueError(f"{connector} board_id has an invalid format")
    if sprint_id is not None and not rules["sprint_id"].match(sprint_id):
        raise ValueError(f"{connector} sprint_id has an invalid format")


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
        validate_connector_scope(self.connector, self.board_id, self.sprint_id)
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
