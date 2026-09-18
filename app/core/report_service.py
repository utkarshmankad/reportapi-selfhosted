"""Core report generation logic — shared by the API route and the Celery beat scheduler."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import reload_runtime_settings
from app.connectors.asana import AsanaConnector
from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector
from app.core.pii import sanitize_tickets, strip_pii
from app.core.prompt_builder import build_prompt
from app.db.models import Report
from app.llm.factory import get_llm_provider
from app.models.ticket import Ticket


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


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def filter_by_period(
    tickets: list[Ticket], period_start: datetime | None, period_end: datetime | None
) -> list[Ticket]:
    """
    The reporting period is defined as "tickets updated within
    [period_start, period_end]" — an activity window, not a claim about
    historical ticket state at any point in that window (the source APIs
    only expose current state, not point-in-time snapshots).
    """
    if period_start is None and period_end is None:
        return tickets
    start = _as_utc(period_start) if period_start else None
    end = _as_utc(period_end) if period_end else None
    return [
        t
        for t in tickets
        if (start is None or _as_utc(t.updated_at) >= start)
        and (end is None or _as_utc(t.updated_at) <= end)
    ]


async def generate_report(
    db: AsyncSession,
    connector: str,
    board_id: str | None,
    sprint_id: str | None,
    output_format: str = "text",
    assigned_means_in_progress: bool = True,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> tuple[Report, int]:
    """
    Fetch tickets, strip PII, generate a narrative, persist the report.
    Returns (report, ticket_count). Raises ReportGenerationError on any failure.
    """
    config = reload_runtime_settings()
    connectors = {"jira": JiraConnector, "asana": AsanaConnector, "github": GitHubConnector}
    if connector not in connectors:
        raise ReportGenerationError(
            400, f"Connector '{connector}' not supported. Available: {', '.join(connectors)}."
        )

    if not board_id and not sprint_id:
        raise ReportGenerationError(422, "Either board_id or sprint_id is required")

    try:
        source = connectors[connector](config)
    except ValueError as e:
        raise ReportGenerationError(500, str(e))

    try:
        fetch_result = await source.fetch(
            {
                "board_id": board_id,
                "sprint_id": sprint_id,
                "assigned_means_in_progress": assigned_means_in_progress,
            }
        )
    except Exception:
        raise ReportGenerationError(
            502, f"{connector.capitalize()} fetch failed; check connection settings"
        )

    tickets = fetch_result.tickets
    if not tickets:
        raise ReportGenerationError(422, "No tickets found for the given filter")

    tickets = dedupe_tickets(tickets)
    tickets = filter_by_period(tickets, period_start, period_end)
    if not tickets:
        raise ReportGenerationError(422, "No tickets updated within the given period")

    period_semantics = (
        "tickets_updated_in_range" if (period_start or period_end) else "unbounded_fetch_snapshot"
    )

    sanitize_tickets(tickets)

    system_prompt, user_content, excluded_ticket_count = build_prompt(
        tickets, config.max_tokens_output, config.max_tokens_input, period_start, period_end
    )

    try:
        llm = get_llm_provider(config)
        narrative, tokens_used, provider_truncated = await llm.generate(
            system_prompt=system_prompt,
            user_content=strip_pii(user_content),
            max_tokens=config.max_tokens_output,
        )
    except Exception:
        raise ReportGenerationError(500, "Report generation failed; check provider settings")

    if not narrative or not narrative.strip():
        raise ReportGenerationError(502, "Provider returned an empty report; try again")

    is_truncated = fetch_result.truncated or excluded_ticket_count > 0 or provider_truncated
    reasons = []
    if fetch_result.truncation_reason:
        reasons.append(fetch_result.truncation_reason)
    if excluded_ticket_count:
        reasons.append(f"{excluded_ticket_count} ticket(s) omitted from the LLM input size budget")
    if provider_truncated:
        reasons.append("Provider cut the narrative off at its output token limit")
    truncation_reason = "; ".join(reasons) or None

    report = Report(
        connector=connector,
        status="partial" if is_truncated else "complete",
        model_used=config.llm_provider,
        tokens_used=tokens_used,
        narrative=narrative,
        output_format=output_format,
        is_truncated=is_truncated,
        truncation_reason=truncation_reason,
        period_start=period_start,
        period_end=period_end,
        period_semantics=period_semantics,
    )
    try:
        db.add(report)
        await db.commit()
        await db.refresh(report)
    except Exception:
        await db.rollback()
        raise ReportGenerationError(500, "Failed to persist the generated report")

    return report, len(tickets)
