"""Report template upload routes — templates render sandboxed, no OS/filesystem access."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.template_renderer import TemplateRenderError, render_template, validate_template
from app.db.models import Report, ReportJob, ReportTemplate
from app.db.session import get_db
from app.models.template import (
    CreateTemplateRequest,
    TemplatePreviewResponse,
    TemplateResponse,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])

_SAMPLE_NARRATIVE = (
    "Total tickets: 12 (blocked: 1, done: 7, in_progress: 3, todo: 1)\n\n"
    "Sample preview narrative — this is placeholder text standing in for a "
    "generated report, so you can check layout and styling before using this "
    "template for real."
)


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
async def list_templates(
    include_archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    query = select(ReportTemplate).order_by(ReportTemplate.created_at.desc())
    if not include_archived:
        query = query.where(ReportTemplate.archived.is_(False))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await db.get(ReportTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/{template_id}/preview", response_model=TemplatePreviewResponse)
async def preview_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await get_template(template_id, db)
    sample = Report(
        connector="jira",
        status="complete",
        model_used="preview",
        tokens_used=0,
        narrative=_SAMPLE_NARRATIVE,
        output_format="pdf",
        created_at=datetime.now(timezone.utc),
    )
    try:
        html = await run_in_threadpool(render_template, template.content, sample)
    except TemplateRenderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TemplatePreviewResponse(html=html)


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
    # Bumped on every edit: reports snapshot this value (Report.template_version)
    # so a rendered report is always traceable to the exact template content
    # that produced it, distinct from any later edit.
    template.version += 1
    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/archive", response_model=TemplateResponse)
async def archive_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await get_template(template_id, db)
    template.archived = True
    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/restore", response_model=TemplateResponse)
async def restore_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await get_template(template_id, db)
    template.archived = False
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await get_template(template_id, db)

    report_count = (
        await db.execute(
            select(func.count()).select_from(Report).where(Report.template_id == template_id)
        )
    ).scalar_one()
    job_count = (
        await db.execute(
            select(func.count()).select_from(ReportJob).where(ReportJob.template_id == template_id)
        )
    ).scalar_one()
    if report_count or job_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "This template is referenced by existing reports or jobs. "
                "Archive it instead of deleting it to preserve those historical references."
            ),
        )

    await db.delete(template)
    await db.commit()
