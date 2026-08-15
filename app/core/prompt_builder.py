"""Prompt construction for LLM providers."""
from collections import defaultdict
from datetime import datetime, timezone
from app.models.ticket import Ticket

STALE_DAYS_THRESHOLD = 3

SYSTEM_PROMPT_TEMPLATE = """You are a senior engineering analyst writing a status report for a \
director. The director reads dozens of these — they want facts they can act \
on, not prose.

Hard rules:
- Open with one line: total ticket count and the exact breakdown by status \
(done / in progress / blocked / todo). Use the numbers given in the input \
verbatim — never approximate with words like "a number of" or "several".
- Do not invent data not present in the input.
- Never write scene-setting or transition sentences that carry no \
information ("This demonstrates progress", "Overall, our sprint is \
progressing", "Close monitoring will be crucial", etc). If a sentence would \
still be true for any sprint on any team, cut it.
- Blocked tickets: report ONLY tickets whose status is exactly "blocked", by \
title and assignee. If none are blocked, state that in one sentence and \
stop — do not speculate that other tickets "might" be blocked or that TODOs \
"suggest" hidden dependencies. A report must not hedge on its own claims.
- For each assignee, name what they own (ticket titles, not just counts) and \
flag it explicitly if any of their items has gone STALE_DAYS_THRESHOLD+ days \
without an update — the input marks this for you.
- Risk section (required): call out by name any ticket that is stale, \
marked high/critical priority, or blocked — with a one-line reason. If \
genuinely nothing is at risk, say so in one sentence.
- No closing summary paragraph. End after the risk section.
- Maximum length: {max_tokens} tokens.
"""


def _days_since(dt: datetime) -> int:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def build_prompt(tickets: list[Ticket], max_tokens: int) -> tuple[str, str]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(max_tokens=max_tokens)

    status_counts: dict[str, int] = defaultdict(int)
    for t in tickets:
        status_counts[t.status] += 1

    counts_line = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))

    lines = [f"Total tickets: {len(tickets)} ({counts_line})", ""]

    lines.append("Tickets:")
    for t in tickets:
        stale_days = _days_since(t.updated_at)
        is_stale = stale_days >= STALE_DAYS_THRESHOLD and t.status in ("in_progress", "blocked")
        line = f"- [{t.status.upper()}] {t.title}"
        if t.assignee:
            line += f" | assignee: {t.assignee}"
        if t.priority:
            line += f" | priority: {t.priority}"
        line += f" | last updated {stale_days}d ago"
        if is_stale:
            line += " | STALE (no update >= {}d)".format(STALE_DAYS_THRESHOLD)
        lines.append(line)

    lines.append("")
    assignee_map: dict[str, list[Ticket]] = defaultdict(list)
    for t in tickets:
        if t.assignee:
            assignee_map[t.assignee].append(t)

    lines.append("By assignee:")
    if assignee_map:
        for assignee, owned in sorted(assignee_map.items()):
            titles = "; ".join(f"{o.title} ({o.status})" for o in owned)
            lines.append(f"- {assignee}: {len(owned)} ticket(s) — {titles}")
    else:
        lines.append("- No tickets have an assignee.")

    blocked = [t for t in tickets if t.status == "blocked"]
    lines.append("")
    lines.append(f"Blocked tickets ({len(blocked)}):")
    if blocked:
        for t in blocked:
            lines.append(f"- {t.title} (assignee: {t.assignee or 'unassigned'})")
    else:
        lines.append("- None.")

    user_content = "\n".join(lines)

    return system_prompt, user_content
