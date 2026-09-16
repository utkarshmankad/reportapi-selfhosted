"""Ticket pydantic schema."""

from datetime import datetime

from pydantic import BaseModel


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    status: str  # normalised: todo / in_progress / done / blocked
    assignee: str | None
    priority: str | None
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    sprint: str | None
    url: str
