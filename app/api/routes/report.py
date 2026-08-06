"""Report generation routes."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report import GenerateReportRequest, GenerateReportResponse
from app.connectors.jira import JiraConnector
from app.core.pii import strip_pii_from_ticket
from app.core.prompt_builder import build_prompt
from app.llm.factory import get_llm_provider
from app.db.session import get_db
from app.db.models import Report
from app.config import settings

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report/generate", response_model=GenerateReportResponse)
async def generate_report(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
):
    if request.connector != "jira":
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{request.connector}' not supported in v0.1. Only 'jira' is available.",
        )

    if not request.board_id and not request.sprint_id:
        raise HTTPException(
            status_code=422,
            detail="Either board_id or sprint_id is required",
        )

    try:
        connector = JiraConnector()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        tickets = await connector.fetch({
            "board_id": request.board_id,
            "sprint_id": request.sprint_id,
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Jira fetch failed: {str(e)}")

    if not tickets:
        raise HTTPException(status_code=422, detail="No tickets found for the given filter")

    for ticket in tickets:
        strip_pii_from_ticket(ticket)

    system_prompt, user_content = build_prompt(tickets, settings.max_tokens_output)

    try:
        llm = get_llm_provider()
        narrative, tokens_used = await llm.generate(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=settings.max_tokens_output,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

    report = Report(
        connector=request.connector,
        status="complete",
        model_used=settings.llm_provider,
        tokens_used=tokens_used,
        narrative=narrative,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return GenerateReportResponse(
        report_id=report.id,
        status="complete",
        narrative=narrative,
        tokens_used=tokens_used,
        model_used=settings.llm_provider,
        ticket_count=len(tickets),
    )
