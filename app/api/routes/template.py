"""Report template upload routes — templates render sandboxed, no OS/filesystem access."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.template_renderer import TemplateRenderError, validate_template
from app.db.models import ReportTemplate
from app.db.session import get_db
from app.models.template import CreateTemplateRequest, TemplateResponse

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("", response_model=TemplateResponse)
async def upload_template(request: CreateTemplateRequest, db: AsyncSession = Depends(get_db)):
    try:
        await run_in_threadpool(validate_template, request.content)
    except TemplateRenderError as e:
        raise HTTPException(status_code=422, detail=str(e))

    template = ReportTemplate(name=request.name, content=request.content)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("", response_model=list[TemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReportTemplate).order_by(ReportTemplate.created_at.desc()))
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await db.get(ReportTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID, request: CreateTemplateRequest, db: AsyncSession = Depends(get_db)
):
    template = await get_template(template_id, db)
    try:
        await run_in_threadpool(validate_template, request.content)
    except TemplateRenderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    template.name = request.name
    template.content = request.content
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await get_template(template_id, db)
    await db.delete(template)
    await db.commit()
