"""Report generation routes."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report import GenerateReportRequest, GenerateReportResponse
from app.core.report_service import generate_report, ReportGenerationError
from app.core.template_renderer import (
    render_template, render_markdown, TemplateRenderError, DEFAULT_TEMPLATE,
)
from app.core.pdf_renderer import render_pdf
from app.db.session import get_db
from app.db.models import Report, ReportTemplate

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report/generate", response_model=GenerateReportResponse)
async def generate_report_route(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
):
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
            html = render_template(template_content, report)
            pdf_bytes = render_pdf(html)
        except TemplateRenderError as e:
            raise HTTPException(status_code=422, detail=str(e))

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="report-{report.id}.pdf"'},
        )

    raise HTTPException(status_code=422, detail="format must be text, markdown, or pdf")
