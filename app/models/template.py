"""Report template pydantic schema."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50000)


class TemplateResponse(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50000)
    version: int
    archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplatePreviewResponse(BaseModel):
    html: str
