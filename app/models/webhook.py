"""Webhook destination/delivery pydantic schema."""

import secrets
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateWebhookDestinationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    active: bool = True

    @field_validator("url")
    @classmethod
    def valid_http_url(cls, value: str) -> str:
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("url must be an http:// or https:// URL")
        return value


class WebhookDestinationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    url: str
    active: bool
    created_at: datetime


class WebhookDestinationCreatedResponse(WebhookDestinationResponse):
    # The signing secret is only ever returned once, at creation — it's
    # not retrievable afterward, the same way an API key isn't.
    secret: str


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    destination_id: UUID
    report_id: UUID
    status: Literal["pending", "delivered", "failed"]
    attempts: int
    response_status: int | None
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None
