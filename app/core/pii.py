"""PII detection and stripping."""

import ipaddress
import re

AADHAAR_RE = re.compile(r"\b[2-9]\d{11}\b")
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
IN_PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")


def luhn_check(number: str) -> bool:
    digits = [int(d) for d in number]
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


CARD_RE = re.compile(r"(?<!\d)(?=(\d(?:[ -]?\d){12,18}(?!\d)))")
IP_RE = re.compile(
    r"(?<![\w:])(?:[0-9a-fA-F]*:){2,}[0-9a-fA-F:.]*(?:%[\w.-]+)?"
    r"|(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)"
)


def _card_spans(text: str):
    # Overlapping lookahead prevents an adjacent number (e.g. "Person 1")
    # from hiding a card. Only complete digit groups are considered.
    spans = []
    for match in CARD_RE.finditer(text):
        candidate = match[1]
        for end in range(len(candidate), 12, -1):
            if not candidate[end - 1].isdigit():
                continue
            if end < len(candidate) and candidate[end].isdigit():
                continue
            digits = re.sub(r"[ -]", "", candidate[:end])
            if 13 <= len(digits) <= 19 and luhn_check(digits):
                spans.append((match.start(), match.start() + end, digits))
                break
    return spans


def find_credit_cards(text: str) -> list[str]:
    return [digits for _, _, digits in _card_spans(text)]


def _strip_cards(text: str) -> str:
    spans = _card_spans(text)
    merged = []
    for start, end, _ in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + "[REDACTED_CARD]" + text[end:]
    return text


def _strip_ip(match):
    candidate = match[0].rstrip(".")
    suffix = match[0][len(candidate) :]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return match[0]
    return "[REDACTED_IP]" + suffix


def strip_pii(text: str) -> str:
    """Redact supported identifiers; this is not general-purpose anonymization."""
    if not text:
        return text
    cleaned = _strip_cards(text)
    cleaned = IP_RE.sub(_strip_ip, cleaned)
    cleaned = AADHAAR_RE.sub("[REDACTED_ID]", cleaned)
    cleaned = PAN_RE.sub("[REDACTED_ID]", cleaned)
    cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
    return IN_PHONE_RE.sub("[REDACTED_PHONE]", cleaned)


def sanitize_tickets(tickets) -> None:
    """Apply report-local aliases and scrub every textual ticket field in place.

    Only names actually supplied as assignees can be recognized in prose.
    The alias map exists only during this call and is never persisted.
    """
    names = sorted(
        {t.assignee.strip().casefold() for t in tickets if t.assignee and t.assignee.strip()}
    )
    aliases = {name: f"Person {index + 1}" for index, name in enumerate(names)}
    pattern = (
        re.compile(
            r"(?<!\w)(?:"
            + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            + r")(?!\w)",
            re.IGNORECASE,
        )
        if names
        else None
    )

    def clean(value):
        value = strip_pii(value)
        if pattern:
            value = pattern.sub(lambda m: aliases[m[0].casefold()], value)
        return strip_pii(value)

    for ticket in tickets:
        assignee = ticket.assignee
        for field in ("title", "description", "status", "priority", "sprint", "url"):
            value = getattr(ticket, field)
            if value is not None:
                setattr(ticket, field, clean(value))
        ticket.labels = [clean(label) for label in ticket.labels]
        ticket.assignee = aliases.get(assignee.strip().casefold()) if assignee else None


def strip_pii_from_ticket(ticket) -> None:
    sanitize_tickets([ticket])
