"""Prompt construction for LLM providers."""

import re
from collections import defaultdict
from datetime import datetime, timezone

from app.models.ticket import Ticket

STALE_DAYS_THRESHOLD = 3
HIGH_PRIORITY_VALUES = {"high", "critical", "p0", "p1"}

# Cross-references that mark two tickets as the same underlying issue
# (e.g. a tracking ticket plus the specific advisory it tracks) so they
# collapse into one risk entry instead of double-counting. Deliberately
# broad — includes bare "#123" issue links — because for de-duplication
# purposes any shared reference is worth surfacing.
_XREF_PATTERN = re.compile(r"RUSTSEC-\d{4}-\d+|CVE-\d{4}-\d+|#\d+", re.IGNORECASE)

# Security-advisory identifiers only. Deliberately NARROWER than
# _XREF_PATTERN: a bare "#123" is just an issue cross-reference (e.g.
# "duplicate of #123", "blocks #456") and says nothing about security —
# using the broad xref pattern here previously mislabeled ordinary
# feature/bugfix tickets as security advisories any time their
# description happened to link another issue.
_SECURITY_ADVISORY_PATTERN = re.compile(r"RUSTSEC-\d{4}-\d+|CVE-\d{4}-\d+", re.IGNORECASE)

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
tier (CRITICAL / HIGH / MEDIUM), grouped by tier, CRITICAL first. Use the \
exact reason given in the input for each — never assert a tier without \
restating its reason (e.g. "HIGH — stale 10d, security advisory", not just \
"HIGH"). Two tickets referencing the same tracking ID or advisory (the \
input marks these as RELATED) are ONE risk entry, not two — merge them. If \
the input marks no risk tickets, say so in one sentence.
- Ownership gap (required if the input's "Unassigned" line has a nonzero \
count): report it as its own risk-level line, not folded into the assignee \
paragraph — e.g. "N of M tickets (X%) have no assignee." A large unowned \
share is itself a risk to call out, not a footnote.
- No closing summary paragraph. End after the risk section.
- The input states a reporting period. State it once, in your own words, \
alongside the opening count line. Never claim a ticket was in a given state \
"throughout" or "during" the period, or reconstruct a history of status \
changes — the input is current/updated-in-range state only, not a \
timeline of events.
- Maximum length: {{max_tokens}} tokens.
""".format(
    stale_days=STALE_DAYS_THRESHOLD,
)


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
    return bool(
        _SECURITY_ADVISORY_PATTERN.search(t.title)
        or _SECURITY_ADVISORY_PATTERN.search(t.description or "")
    )


def _risk_tier_and_reason(t: Ticket, is_stale: bool, stale_days: int) -> tuple[str, str] | None:
    security = _is_security(t)
    high_pri = _is_high_priority(t.priority)

    if t.status == "blocked":
        if high_pri or security:
            reason = "blocked" + (", security advisory" if security else f", priority {t.priority}")
            return "CRITICAL", reason
        return "HIGH", "blocked, no priority set"

    if is_stale and (high_pri or security):
        reason = f"stale {stale_days}d" + (
            ", security advisory" if security else f", priority {t.priority}"
        )
        return "HIGH", reason

    if is_stale:
        return "MEDIUM", f"stale {stale_days}d, no priority/security signal"

    return None


def _xref_groups(tickets: list[Ticket]) -> dict[str, list[Ticket]]:
    groups: dict[str, list[Ticket]] = defaultdict(list)
    for t in tickets:
        refs = {m.upper() for m in _XREF_PATTERN.findall(f"{t.title} {t.description or ''}")}
        for ref in refs:
            groups[ref].append(t)
    return {k: v for k, v in groups.items() if len(v) > 1}


# Rough, provider-agnostic token estimate (~4 characters/token). This is
# deliberately conservative rather than exact — an approximation is enough
# to decide whether the ticket listing needs trimming to fit the configured
# input budget; it is not used for billing or provider-reported usage.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _ticket_rank_key(t: Ticket, risk_by_id: dict[str, tuple[str, str]]) -> tuple[int, str]:
    """Deterministic priority for which tickets survive an input-budget cut.

    Lower sorts first (kept first): blocked tickets, then anything flagged
    as a risk, then everything else — tied within a tier by ticket id so
    the same input always produces the same trimmed set.
    """
    if t.status == "blocked":
        tier = 0
    elif t.id in risk_by_id:
        tier = 1
    else:
        tier = 2
    return (tier, t.id)


def build_prompt(
    tickets: list[Ticket],
    max_tokens: int,
    max_input_tokens: int,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> tuple[str, str, int]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(max_tokens=max_tokens)

    status_counts: dict[str, int] = defaultdict(int)
    for t in tickets:
        status_counts[t.status] += 1

    counts_line = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))

    lines = [f"Total tickets: {len(tickets)} ({counts_line})"]
    if period_start or period_end:
        lines.append(
            f"Reporting period: tickets updated from {period_start or 'the beginning'} to "
            f"{period_end or 'now'}. This reflects activity in that window only — it is not a "
            "claim about ticket state at any specific point in time within it."
        )
    else:
        lines.append(
            "Reporting period: unbounded — this is a snapshot of current ticket state as of "
            "when the report was generated, not a historical reconstruction."
        )
    lines.append("")

    risk_by_id: dict[str, tuple[str, str]] = {}
    ticket_lines: dict[str, str] = {}
    stale_by_id: dict[str, int] = {}

    for t in tickets:
        stale_days = _days_since(t.updated_at)
        is_stale = stale_days >= STALE_DAYS_THRESHOLD and t.status in ("in_progress", "blocked")
        stale_by_id[t.id] = stale_days

        line = f"- [{t.status.upper()}] {t.title}"
        if t.assignee:
            line += f" | assignee: {t.assignee}"
        if t.priority:
            line += f" | priority: {t.priority}"
        line += f" | last updated {stale_days}d ago"
        if is_stale:
            line += f" | STALE (no update >= {STALE_DAYS_THRESHOLD}d)"

        tier_reason = _risk_tier_and_reason(t, is_stale, stale_days)
        if tier_reason:
            risk_by_id[t.id] = tier_reason
            line += f" | RISK: {tier_reason[0]} ({tier_reason[1]})"

        ticket_lines[t.id] = line

    # Reserve a fixed slice of the input budget for everything other than
    # the per-ticket listing (headers, assignee/blocked/risk sections), then
    # deterministically keep as many tickets as fit — blocked and risk
    # tickets first — rather than truncating mid-listing or silently
    # dropping arbitrary tickets.
    reserved_tokens = estimate_tokens("\n".join(lines)) + 500
    budget = max(0, max_input_tokens - reserved_tokens)

    ranked = sorted(tickets, key=lambda t: _ticket_rank_key(t, risk_by_id))
    included_ids: set[str] = set()
    used_tokens = 0
    for t in ranked:
        cost = estimate_tokens(ticket_lines[t.id]) + 1
        if used_tokens + cost > budget and included_ids:
            break
        used_tokens += cost
        included_ids.add(t.id)
        if used_tokens >= budget:
            break

    excluded_count = len(tickets) - len(included_ids)

    lines.append("Tickets:")
    for t in tickets:
        if t.id in included_ids:
            lines.append(ticket_lines[t.id])
    if excluded_count:
        lines.append(
            f"- ... {excluded_count} additional ticket(s) omitted from this listing to stay "
            "within the input size budget (still counted in the totals above; lowest-priority "
            "and non-risk tickets omitted first)."
        )

    lines.append("")
    assignee_map: dict[str, list[Ticket]] = defaultdict(list)
    for t in tickets:
        if t.assignee:
            assignee_map[t.assignee].append(t)

    unassigned_count = len(tickets) - sum(len(v) for v in assignee_map.values())
    unassigned_pct = round(100 * unassigned_count / len(tickets)) if tickets else 0
    lines.append(
        f"Unassigned: {unassigned_count} of {len(tickets)} tickets ({unassigned_pct}%) have no assignee."
    )

    lines.append("")
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
        for tid, (tier, reason) in sorted(risk_by_id.items(), key=lambda kv: tier_order[kv[1][0]]):
            t = by_id[tid]
            lines.append(
                f"- [{tier}] {t.title} (assignee: {t.assignee or 'unassigned'}) — {reason}"
            )
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

    return system_prompt, user_content, excluded_count
