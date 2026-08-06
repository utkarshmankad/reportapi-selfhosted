"""Core report generation logic — shared by the API route and the Celery beat scheduler."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.connectors.jira import JiraConnector
from app.core.pii import strip_pii_from_ticket
from app.core.prompt_builder import build_prompt
from app.llm.factory import get_llm_provider
from app.db.models import Report
from app.config import settings


class ReportGenerationError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def generate_report(
    db: AsyncSession,
    connector: str,
    board_id: str | None,
    sprint_id: str | None,
    output_format: str = "text",
) -> tuple[Report, int]:
    """
    Fetch tickets, strip PII, generate a narrative, persist the report.
    Returns (report, ticket_count). Raises ReportGenerationError on any failure.
    """
    if connector != "jira":
        raise ReportGenerationError(
            400, f"Connector '{connector}' not supported in v0.1. Only 'jira' is available."
        )

    if not board_id and not sprint_id:
        raise ReportGenerationError(422, "Either board_id or sprint_id is required")

    try:
        jira = JiraConnector()
    except ValueError as e:
        raise ReportGenerationError(500, str(e))

    try:
        tickets = await jira.fetch({"board_id": board_id, "sprint_id": sprint_id})
    except Exception as e:
        raise ReportGenerationError(502, f"Jira fetch failed: {str(e)}")

    if not tickets:
        raise ReportGenerationError(422, "No tickets found for the given filter")

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
        raise ReportGenerationError(500, f"Report generation failed: {str(e)}")

    report = Report(
        connector=connector,
        status="complete",
        model_used=settings.llm_provider,
        tokens_used=tokens_used,
        narrative=narrative,
        output_format=output_format,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return report, len(tickets)
