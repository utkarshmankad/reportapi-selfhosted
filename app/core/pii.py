"""PII detection and stripping."""

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


def find_credit_cards(text: str) -> list[str]:
    candidates = re.findall(r"\d{13,19}", text.replace(" ", "").replace("-", ""))
    return [c for c in candidates if luhn_check(c)]


def strip_pii(text: str) -> str:
    """
    Remove regulated personal identifiers from text before it is embedded
    or sent to any LLM. Returns the cleaned text.
    """
    if not text:
        return text

    cleaned = text
    cleaned = AADHAAR_RE.sub("[REDACTED_ID]", cleaned)
    cleaned = PAN_RE.sub("[REDACTED_ID]", cleaned)
    cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
    cleaned = IN_PHONE_RE.sub("[REDACTED_PHONE]", cleaned)

    for card in find_credit_cards(cleaned):
        cleaned = cleaned.replace(card, "[REDACTED_CARD]")

    return cleaned


def strip_pii_from_ticket(ticket) -> None:
    """
    Mutates a Ticket object in place, stripping PII from description
    and title fields only. Does not touch id, status, or url.
    """
    ticket.description = strip_pii(ticket.description)
    ticket.title = strip_pii(ticket.title)
