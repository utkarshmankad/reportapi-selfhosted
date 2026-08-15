"""Core report generation logic — shared by the API route and the Celery beat scheduler."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.connectors.jira import JiraConnector
from app.connectors.asana import AsanaConnector
from app.connectors.github import GitHubConnector
from app.core.pii import strip_pii_from_ticket
from app.models.ticket import Ticket
from app.core.prompt_builder import build_prompt
from app.llm.factory import get_llm_provider
from app.db.models import Report
from app.config import settings


class ReportGenerationError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def dedupe_tickets(tickets: list[Ticket]) -> list[Ticket]:
    """
    Connectors are the source of truth for ticket identity: same id means
    same ticket, full stop. Collapse duplicates here — the layer closest to
    the source data — rather than downstream where "is this the same ticket
    twice or two different tickets" would have to be guessed at. Keeps the
    most-recently-updated record for any id seen more than once.
    """
    deduped: dict[str, Ticket] = {}
    for ticket in tickets:
        existing = deduped.get(ticket.id)
        if existing is None or ticket.updated_at > existing.updated_at:
            deduped[ticket.id] = ticket
    return list(deduped.values())


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
    connectors = {"jira": JiraConnector, "asana": AsanaConnector, "github": GitHubConnector}
    if connector not in connectors:
        raise ReportGenerationError(
            400, f"Connector '{connector}' not supported. Available: {', '.join(connectors)}."
        )

    if not board_id and not sprint_id:
        raise ReportGenerationError(422, "Either board_id or sprint_id is required")

    try:
        source = connectors[connector]()
    except ValueError as e:
        raise ReportGenerationError(500, str(e))

    try:
        tickets = await source.fetch({"board_id": board_id, "sprint_id": sprint_id})
    except Exception as e:
        raise ReportGenerationError(502, f"{connector.capitalize()} fetch failed: {str(e)}")

    if not tickets:
        raise ReportGenerationError(422, "No tickets found for the given filter")

    tickets = dedupe_tickets(tickets)

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
