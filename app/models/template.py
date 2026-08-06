"""Report template pydantic schema."""
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class CreateTemplateRequest(BaseModel):
    name: str
    content: str


class TemplateResponse(BaseModel):
    id: UUID
    name: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
