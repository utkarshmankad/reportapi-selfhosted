from datetime import datetime, timedelta, timezone

from app.core.prompt_builder import build_prompt
from app.models.ticket import Ticket

NOW = datetime.now(timezone.utc)


def _ticket(**overrides):
    defaults = dict(
        id="1",
        title="Some task",
        description="",
        status="in_progress",
        assignee="alice",
        priority=None,
        labels=[],
        created_at=NOW,
        updated_at=NOW,
        sprint=None,
        url="https://example.com",
    )
    defaults.update(overrides)
    return Ticket(**defaults)


def test_status_counts_are_computed_verbatim():
    tickets = [
        _ticket(id="1", status="done"),
        _ticket(id="2", status="done"),
        _ticket(id="3", status="blocked"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Total tickets: 3 (blocked: 1, done: 2)" in user_content


def test_blocked_section_lists_only_blocked_tickets():
    tickets = [
        _ticket(id="1", title="Blocked thing", status="blocked", assignee="bob"),
        _ticket(id="2", title="Not blocked", status="in_progress"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Blocked tickets (1):" in user_content
    assert "- Blocked thing (assignee: bob)" in user_content
    assert "Not blocked" not in user_content.split("Blocked tickets")[1]


def test_no_blocked_tickets_says_none():
    tickets = [_ticket(status="in_progress")]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Blocked tickets (0):" in user_content
    assert "- None." in user_content


def test_stale_ticket_is_flagged():
    stale = _ticket(id="1", status="in_progress", updated_at=NOW - timedelta(days=5))
    fresh = _ticket(id="2", status="in_progress", updated_at=NOW)
    _, user_content, _ = build_prompt([stale, fresh], 800, 12000)
    lines = user_content.splitlines()
    stale_line = next(line for line in lines if "id" not in line and "last updated 5d ago" in line)
    fresh_line = next(line for line in lines if "last updated 0d ago" in line)
    assert "STALE" in stale_line
    assert "STALE" not in fresh_line


def test_done_ticket_never_flagged_stale_regardless_of_age():
    old_done = _ticket(status="done", updated_at=NOW - timedelta(days=30))
    _, user_content, _ = build_prompt([old_done], 800, 12000)
    assert "STALE" not in user_content


def test_assignee_breakdown_lists_owned_titles():
    tickets = [
        _ticket(id="1", title="Task A", assignee="alice", status="in_progress"),
        _ticket(id="2", title="Task B", assignee="alice", status="done"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "- alice: 2 ticket(s) — Task A (in_progress); Task B (done)" in user_content


def test_unassigned_tickets_note_no_assignee():
    tickets = [_ticket(assignee=None)]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "- No tickets have an assignee." in user_content


def test_system_prompt_bans_hedging_and_filler():
    system_prompt, _, _ = build_prompt([], 800, 12000)
    assert "never" in system_prompt.lower() or "must not" in system_prompt.lower()
    assert "800" in system_prompt


def test_blocked_ticket_is_critical_risk_when_high_priority():
    t = _ticket(status="blocked", priority="high", title="Blocked and urgent")
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "[CRITICAL] Blocked and urgent" in user_content


def test_blocked_ticket_is_high_risk_when_no_priority():
    t = _ticket(status="blocked", priority=None, title="Just blocked")
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "[HIGH] Just blocked" in user_content


def test_stale_high_priority_ticket_is_high_risk():
    t = _ticket(
        status="in_progress",
        priority="critical",
        updated_at=NOW - timedelta(days=10),
        title="Stale critical",
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "[HIGH] Stale critical" in user_content


def test_stale_low_priority_ticket_is_medium_risk():
    t = _ticket(
        status="in_progress",
        priority=None,
        updated_at=NOW - timedelta(days=10),
        title="Stale routine",
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "[MEDIUM] Stale routine" in user_content


def test_fresh_low_priority_ticket_is_not_a_risk():
    t = _ticket(status="in_progress", priority=None, updated_at=NOW, title="Totally fine")
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "Risk tickets (0):" in user_content
    assert "Totally fine" not in user_content.split("Risk tickets")[1]


def test_security_advisory_reference_flagged_as_risk_even_without_priority():
    t = _ticket(
        status="in_progress",
        priority=None,
        updated_at=NOW - timedelta(days=5),
        title="RUSTSEC-2026-0235 openssl vuln",
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "[HIGH] RUSTSEC-2026-0235 openssl vuln" in user_content


def test_tracking_ticket_and_advisory_ticket_collapse_into_one_related_entry():
    tracking = _ticket(
        id="1",
        title="Tracking: outstanding RustSec advisories",
        description="parent tracker for RUSTSEC-2026-0235",
    )
    advisory = _ticket(id="2", title="RUSTSEC-2026-0235 openssl vuln")
    _, user_content, _ = build_prompt([tracking, advisory], 800, 12000)
    assert "RELATED (same underlying issue" in user_content
    related_block = user_content.split("RELATED")[1]
    assert "Tracking: outstanding RustSec advisories" in related_block
    assert "RUSTSEC-2026-0235 openssl vuln" in related_block
    # each ticket appears once in the group, not duplicated against itself
    assert related_block.count("RUSTSEC-2026-0235 openssl vuln") == 1


def test_single_ticket_referencing_advisory_id_has_no_related_section():
    t = _ticket(
        title="RUSTSEC-2026-0235 openssl vuln", description="see RUSTSEC-2026-0235 for details"
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    assert "RELATED" not in user_content


def test_uneven_assignee_load_flagged_for_unique_outlier():
    tickets = [
        _ticket(id="1", assignee="alice", status="todo"),
        _ticket(id="2", assignee="alice", status="todo"),
        _ticket(id="3", assignee="alice", status="todo"),
        _ticket(id="4", assignee="bob", status="todo"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Load note: alice has 3 ticket(s)" in user_content


def test_tied_top_assignees_do_not_get_a_misleading_load_note():
    tickets = [
        _ticket(id="1", assignee="alice", status="todo"),
        _ticket(id="2", assignee="alice", status="todo"),
        _ticket(id="3", assignee="bob", status="todo"),
        _ticket(id="4", assignee="bob", status="todo"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Load note" not in user_content


def test_risk_reason_is_stated_not_just_the_tier():
    t = _ticket(
        status="in_progress",
        priority="high",
        updated_at=NOW - timedelta(days=10),
        title="Stale critical",
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    risk_line = next(line for line in user_content.splitlines() if line.startswith("- [HIGH]"))
    assert "stale 10d" in risk_line
    assert "priority high" in risk_line


def test_blocked_high_risk_reason_names_missing_priority():
    t = _ticket(status="blocked", priority=None, title="Just blocked")
    _, user_content, _ = build_prompt([t], 800, 12000)
    risk_line = next(line for line in user_content.splitlines() if line.startswith("- [HIGH]"))
    assert "no priority set" in risk_line


def test_unassigned_count_reported_as_top_level_line():
    tickets = [
        _ticket(id="1", assignee="alice", status="todo"),
        _ticket(id="2", assignee=None, status="todo"),
        _ticket(id="3", assignee=None, status="todo"),
    ]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Unassigned: 2 of 3 tickets (67%) have no assignee." in user_content


def test_zero_unassigned_still_reports_the_line():
    tickets = [_ticket(id="1", assignee="alice", status="todo")]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "Unassigned: 0 of 1 tickets (0%) have no assignee." in user_content


def test_bare_issue_reference_is_not_mislabeled_as_security_advisory():
    # Regression: a ticket that just links another issue ("duplicate of
    # #123", "fixes #456") is not a security advisory. The xref pattern
    # used for RELATED-ticket grouping must not double as the security
    # detector, or ordinary feature/bugfix tickets get tagged as advisories.
    t = _ticket(
        status="in_progress",
        priority=None,
        updated_at=NOW - timedelta(days=5),
        title="Add CancelRequest support",
        description="fixes #999, related to #888",
    )
    _, user_content, _ = build_prompt([t], 800, 12000)
    risk_line = next(line for line in user_content.splitlines() if line.startswith("- [MEDIUM]"))
    assert "security advisory" not in risk_line.lower()
    assert "no priority/security signal" in risk_line


def test_only_real_advisory_ids_are_flagged_security_among_mixed_tickets():
    unrelated = _ticket(
        id="1",
        status="in_progress",
        priority=None,
        title="Mask serving workers",
        description="see also #123",
        updated_at=NOW - timedelta(days=10),
    )
    real_advisory = _ticket(
        id="2",
        status="in_progress",
        priority="high",
        title="RUSTSEC-2026-0235 openssl vuln",
        updated_at=NOW - timedelta(days=10),
    )
    _, user_content, _ = build_prompt([unrelated, real_advisory], 800, 12000)
    risk_block = user_content.split("Risk tickets")[1]
    unrelated_line = next(
        line for line in risk_block.splitlines() if "Mask serving workers" in line
    )
    advisory_line = next(line for line in risk_block.splitlines() if "RUSTSEC-2026-0235" in line)
    assert "security advisory" not in unrelated_line.lower()
    assert "security advisory" in advisory_line


def test_input_budget_keeps_all_tickets_when_under_budget():
    tickets = [_ticket(id=str(i), status="todo") for i in range(5)]
    _, user_content, excluded_count = build_prompt(tickets, 800, 12000)
    assert excluded_count == 0
    assert "omitted from this listing" not in user_content


def test_input_budget_deterministically_excludes_lowest_priority_tickets():
    tickets = [_ticket(id=str(i), title=f"Task {i}", status="todo") for i in range(50)]
    blocked = _ticket(id="blocked-1", title="Must keep", status="blocked")
    tickets.append(blocked)

    _, user_content, excluded_count = build_prompt(tickets, 800, 300)

    assert excluded_count > 0
    assert "omitted from this listing to stay" in user_content
    assert "Must keep" in user_content


def test_input_budget_exclusion_is_deterministic_across_runs():
    tickets = [_ticket(id=str(i), title=f"Task {i}", status="todo") for i in range(50)]
    _, first, first_excluded = build_prompt(tickets, 800, 300)
    _, second, second_excluded = build_prompt(tickets, 800, 300)
    assert first == second
    assert first_excluded == second_excluded


def test_input_budget_never_excludes_when_all_tickets_fit_generous_budget():
    tickets = [_ticket(id=str(i), status="in_progress") for i in range(3)]
    _, user_content, excluded_count = build_prompt(tickets, 800, 1_000_000)
    assert excluded_count == 0


def test_unbounded_period_notes_snapshot():
    tickets = [_ticket()]
    _, user_content, _ = build_prompt(tickets, 800, 12000)
    assert "unbounded" in user_content.lower()
    assert "snapshot" in user_content.lower()


def test_bounded_period_states_range_and_disclaimer():
    tickets = [_ticket()]
    start = NOW - timedelta(days=30)
    end = NOW
    _, user_content, _ = build_prompt(tickets, 800, 12000, start, end)
    assert str(start) in user_content
    assert str(end) in user_content
    assert "not a claim about ticket state at any specific point" in user_content
