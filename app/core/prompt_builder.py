"""Prompt construction for LLM providers."""
from app.models.ticket import Ticket

SYSTEM_PROMPT_TEMPLATE = """You are a senior engineering analyst.
Convert the sprint ticket data below into a concise executive narrative.

Rules:
- Write in clear, professional prose
- Do not invent data not present in the input
- Group by status: highlight what's done, what's in progress, and what's blocked
- Flag blocked tickets explicitly and note if any have been blocked more than 3 days
- Do not include ticket IDs in every sentence — synthesise trends
- Maximum length: {max_tokens} tokens
"""


def build_prompt(tickets: list[Ticket], max_tokens: int) -> tuple[str, str]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(max_tokens=max_tokens)

    ticket_lines = []
    for t in tickets:
        line = f"- [{t.status.upper()}] {t.title}"
        if t.assignee:
            line += f" (assignee: {t.assignee})"
        if t.priority:
            line += f" (priority: {t.priority})"
        ticket_lines.append(line)

    user_content = "Sprint tickets:\n" + "\n".join(ticket_lines)

    return system_prompt, user_content
