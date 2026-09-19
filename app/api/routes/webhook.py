"""Webhook destination CRUD and delivery status/retry routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ssrf_guard import UnsafeURLError, target_policy
from app.core.webhook_service import retry_delivery
from app.db.models import WebhookDelivery, WebhookDestination
from app.db.session import get_db
from app.models.webhook import (
    CreateWebhookDestinationRequest,
    WebhookDeliveryResponse,
    WebhookDestinationCreatedResponse,
    WebhookDestinationResponse,
    generate_webhook_secret,
)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _check_allowed_origin(url: str) -> None:
    try:
        target_policy(url, "webhook")
    except UnsafeURLError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/destinations", response_model=WebhookDestinationCreatedResponse)
async def create_destination(
    request: CreateWebhookDestinationRequest, db: AsyncSession = Depends(get_db)
):
    _check_allowed_origin(request.url)
    destination = WebhookDestination(
        name=request.name,
        url=request.url,
        active=request.active,
        secret=generate_webhook_secret(),
    )
    db.add(destination)
    await db.commit()
    await db.refresh(destination)
    return destination


@router.get("/destinations", response_model=list[WebhookDestinationResponse])
async def list_destinations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WebhookDestination).order_by(WebhookDestination.created_at.desc())
    )
    return result.scalars().all()


@router.put("/destinations/{destination_id}", response_model=WebhookDestinationResponse)
async def update_destination(
    destination_id: UUID,
    request: CreateWebhookDestinationRequest,
    db: AsyncSession = Depends(get_db),
):
    destination = await db.get(WebhookDestination, destination_id)
    if not destination:
        raise HTTPException(status_code=404, detail="Destination not found")
    _check_allowed_origin(request.url)
    destination.name = request.name
    destination.url = request.url
    destination.active = request.active
    await db.commit()
    await db.refresh(destination)
    return destination


@router.delete("/destinations/{destination_id}", status_code=204)
async def delete_destination(destination_id: UUID, db: AsyncSession = Depends(get_db)):
    destination = await db.get(WebhookDestination, destination_id)
    if not destination:
        raise HTTPException(status_code=404, detail="Destination not found")
    await db.delete(destination)
    await db.commit()


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    destination_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(WebhookDelivery)
        .order_by(WebhookDelivery.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if destination_id:
        query = query.where(WebhookDelivery.destination_id == destination_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/deliveries/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
async def retry_delivery_route(delivery_id: UUID, db: AsyncSession = Depends(get_db)):
    delivery = await db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return await retry_delivery(db, delivery)
