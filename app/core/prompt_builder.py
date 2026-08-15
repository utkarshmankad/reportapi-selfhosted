"""Prompt construction for LLM providers."""
import re
from collections import defaultdict
from datetime import datetime, timezone
from app.models.ticket import Ticket

STALE_DAYS_THRESHOLD = 3
HIGH_PRIORITY_VALUES = {"high", "critical", "p0", "p1"}

# Cross-references that mark two tickets as the same underlying issue
# (e.g. a tracking ticket plus the specific advisory it tracks) so they
# collapse into one risk entry instead of double-counting.
_XREF_PATTERN = re.compile(r"RUSTSEC-\d{4}-\d+|CVE-\d{4}-\d+|#\d+", re.IGNORECASE)

SYSTEM_PROMPT_TEMPLATE = """You are a senior engineering analyst writing a status report for a \
director. The director reads dozens of these — they want facts they can act \
on, not prose.

Hard rules:
- Open with one line: total ticket count and the exact breakdown by status \
(done / in progress / blocked / todo). Use the numbers given in the input \
verbatim — never approximate with words like "a number of" or "several". \
"todo" means not yet started; "in progress" means actively being worked. \
Never merge the two into one bucket.
- Do not invent data not present in the input.
- Never write scene-setting or transition sentences that carry no \
information ("This demonstrates progress", "Overall, our sprint is \
progressing", "Close monitoring will be crucial", etc). If a sentence would \
still be true for any sprint on any team, cut it.
- Blocked tickets: report ONLY tickets whose status is exactly "blocked", by \
title and assignee. If none are blocked, state that in one sentence and \
stop — do not speculate that other tickets "might" be blocked or that TODOs \
"suggest" hidden dependencies. A report must not hedge on its own claims.
- For each assignee, name what they own (ticket titles, not just counts). \
The input tells you each assignee's ticket count — if the load is uneven, \
say so in one line (who has more, who has less). Don't invent a workload \
claim if the input doesn't flag one.
- "Stale" means no update in {stale_days}+ days — the input marks this for \
you per ticket. Use that exact definition; don't redefine it.
- Risk section (required): list every ticket the input marks with a risk \
tier (CRITICAL / HIGH / MEDIUM), grouped by tier, CRITICAL first, each with \
a one-line reason. Two tickets referencing the same tracking ID or advisory \
(the input marks these as RELATED) are ONE risk entry, not two — merge them. \
If the input marks no risk tickets, say so in one sentence.
- No closing summary paragraph. End after the risk section.
- Maximum length: {{max_tokens}} tokens.
""".format(stale_days=STALE_DAYS_THRESHOLD, max_tokens="{max_tokens}")


def _days_since(dt: datetime) -> int:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _is_high_priority(priority: str | None) -> bool:
    if not priority:
        return False
    lowered = priority.strip().lower()
    return any(v in lowered for v in HIGH_PRIORITY_VALUES)


def _is_security(t: Ticket) -> bool:
    if any("security" in label.lower() for label in t.labels):
        return True
    return bool(_XREF_PATTERN.search(t.title) or _XREF_PATTERN.search(t.description or ""))


def _risk_tier(t: Ticket, is_stale: bool) -> str | None:
    if t.status == "blocked":
        return "CRITICAL" if (_is_high_priority(t.priority) or _is_security(t)) else "HIGH"
    if is_stale and (_is_high_priority(t.priority) or _is_security(t)):
        return "HIGH"
    if is_stale:
        return "MEDIUM"
    return None


def _xref_groups(tickets: list[Ticket]) -> dict[str, list[Ticket]]:
    groups: dict[str, list[Ticket]] = defaultdict(list)
    for t in tickets:
        refs = {m.upper() for m in _XREF_PATTERN.findall(f"{t.title} {t.description or ''}")}
        for ref in refs:
            groups[ref].append(t)
    return {k: v for k, v in groups.items() if len(v) > 1}


def build_prompt(tickets: list[Ticket], max_tokens: int) -> tuple[str, str]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(max_tokens=max_tokens)

    status_counts: dict[str, int] = defaultdict(int)
    for t in tickets:
        status_counts[t.status] += 1

    counts_line = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))

    lines = [f"Total tickets: {len(tickets)} ({counts_line})", ""]

    stale_by_id: dict[str, bool] = {}
    risk_by_id: dict[str, str] = {}

    lines.append("Tickets:")
    for t in tickets:
        stale_days = _days_since(t.updated_at)
        is_stale = stale_days >= STALE_DAYS_THRESHOLD and t.status in ("in_progress", "blocked")
        stale_by_id[t.id] = is_stale

        line = f"- [{t.status.upper()}] {t.title}"
        if t.assignee:
            line += f" | assignee: {t.assignee}"
        if t.priority:
            line += f" | priority: {t.priority}"
        line += f" | last updated {stale_days}d ago"
        if is_stale:
            line += f" | STALE (no update >= {STALE_DAYS_THRESHOLD}d)"

        tier = _risk_tier(t, is_stale)
        if tier:
            risk_by_id[t.id] = tier
            line += f" | RISK: {tier}"

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

        counts = [len(v) for v in assignee_map.values()]
        top_count = max(counts)
        top_holders = [name for name, owned in assignee_map.items() if len(owned) == top_count]
        if len(assignee_map) > 1 and top_count > min(counts) and len(top_holders) == 1:
            lines.append(
                f"- Load note: {top_holders[0]} has {top_count} ticket(s), "
                f"more than everyone else (max {min(c for c in counts if c != top_count)})."
            )
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

    lines.append("")
    lines.append(f"Risk tickets ({len(risk_by_id)}):")
    if risk_by_id:
        tier_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        by_id = {t.id: t for t in tickets}
        for tid, tier in sorted(risk_by_id.items(), key=lambda kv: tier_order[kv[1]]):
            t = by_id[tid]
            lines.append(f"- [{tier}] {t.title} (assignee: {t.assignee or 'unassigned'})")
    else:
        lines.append("- None.")

    xrefs = _xref_groups(tickets)
    if xrefs:
        lines.append("")
        lines.append("RELATED (same underlying issue — merge into one risk entry):")
        for ref, group in xrefs.items():
            titles = "; ".join(t.title for t in group)
            lines.append(f"- {ref}: {titles}")

    user_content = "\n".join(lines)

    return system_prompt, user_content
