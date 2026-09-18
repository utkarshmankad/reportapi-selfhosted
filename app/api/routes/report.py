"""Report generation routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.report_service import ReportGenerationError, generate_report
from app.core.template_renderer import (
    DEFAULT_TEMPLATE,
    TemplateRenderError,
    render_markdown,
    render_report_pdf,
)
from app.db.models import Report, ReportTemplate
from app.db.session import get_db
from app.models.report import GenerateReportRequest, GenerateReportResponse, ReportResponse

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report/generate", response_model=GenerateReportResponse)
async def generate_report_route(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
):
    if request.template_id:
        raise HTTPException(status_code=422, detail="Select templates on the render endpoint")
    try:
        report, ticket_count = await generate_report(
            db=db,
            connector=request.connector,
            board_id=request.board_id,
            sprint_id=request.sprint_id,
            output_format=request.output_format,
        )
    except ReportGenerationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return GenerateReportResponse(
        report_id=report.id,
        status=report.status,
        narrative=report.narrative,
        tokens_used=report.tokens_used,
        model_used=report.model_used,
        ticket_count=ticket_count,
        output_format=report.output_format,
    )


@router.get("/report/{report_id}/render")
async def render_report(
    report_id: UUID,
    format: str = "text",
    template_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if format == "text":
        return Response(content=report.narrative, media_type="text/plain")

    if format == "markdown":
        return Response(content=render_markdown(report), media_type="text/markdown")

    if format == "pdf":
        template_content = DEFAULT_TEMPLATE
        if template_id:
            template = await db.get(ReportTemplate, template_id)
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            template_content = template.content

        try:
            pdf_bytes = await run_in_threadpool(render_report_pdf, template_content, report)
        except TemplateRenderError as e:
            raise HTTPException(status_code=422, detail=str(e))

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="report-{report.id}.pdf"'},
        )

    raise HTTPException(status_code=422, detail="format must be text, markdown, or pdf")


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report).order_by(Report.created_at.desc(), Report.id).offset(offset).limit(limit)
    )
    return result.scalars().all()


@router.get("/report/{report_id}", response_model=ReportResponse)
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.delete("/report/{report_id}", status_code=204)
async def delete_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    report = await get_report(report_id, db)
    await db.delete(report)
    await db.commit()
