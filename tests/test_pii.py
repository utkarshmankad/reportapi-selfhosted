from datetime import datetime, timezone

import pytest

from app.core.pii import find_credit_cards, luhn_check, sanitize_tickets, strip_pii
from app.models.ticket import Ticket


def test_strips_aadhaar():
    text = "Contact user with ID 234567890123 for details"
    result = strip_pii(text)
    assert "234567890123" not in result
    assert "[REDACTED_ID]" in result


def test_strips_pan():
    text = "PAN number is ABCDE1234F for verification"
    result = strip_pii(text)
    assert "ABCDE1234F" not in result


def test_strips_email():
    text = "Reach out to jane.doe@company.com for approval"
    result = strip_pii(text)
    assert "jane.doe@company.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_strips_indian_phone():
    text = "Call 9876543210 to confirm the deployment window"
    result = strip_pii(text)
    assert "9876543210" not in result


def test_leaves_normal_text_untouched():
    text = "Fix the login bug affecting Safari users on checkout page"
    result = strip_pii(text)
    assert result == text


def test_luhn_check_valid_card():
    assert luhn_check("4111111111111111") is True


def test_luhn_check_invalid_number():
    assert luhn_check("1234567890123456") is False


def test_empty_string_returns_empty():
    assert strip_pii("") == ""


def test_none_returns_none():
    assert strip_pii(None) is None


@pytest.mark.parametrize("card", ["4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111"])
def test_formatted_cards_replace_original_span(card):
    assert strip_pii(f"Pay {card} now") == "Pay [REDACTED_CARD] now"
    assert find_credit_cards(card) == ["4111111111111111"]
    assert strip_pii("1234-5678-9012-3456") == "1234-5678-9012-3456"


@pytest.mark.parametrize(
    "address", ["192.0.2.1", "2001:db8::1", "::1", "fe80::1%eth0", "::ffff:192.0.2.1"]
)
def test_strips_ip_addresses(address):
    assert strip_pii(f"Host [{address}] failed") == "Host [[REDACTED_IP]] failed"


def test_aliases_are_consistent_across_fields_and_ticket_order():
    now = datetime.now(timezone.utc)

    def ticket(name):
        return Ticket(
            id=name,
            title="Alice Smith and Bob Jones",
            description="Alice Smith",
            status="todo",
            assignee=name,
            priority="high Bob Jones alice@example.com",
            labels=["Alice Smith"],
            sprint="Bob Jones",
            url="https://example.com",
            created_at=now,
            updated_at=now,
        )

    rows = [ticket("Bob Jones"), ticket("Alice Smith"), ticket("alice smith")]
    sanitize_tickets(rows)
    assert [t.assignee for t in rows] == ["Person 2", "Person 1", "Person 1"]
    for row in rows:
        assert row.title == "Person 1 and Person 2"
        assert row.description == "Person 1"
        assert row.priority == "high Person 2 [REDACTED_EMAIL]"
        assert row.labels == ["Person 1"]
        assert row.sprint == "Person 2"
    other_report = [ticket("Bob Jones")]
    sanitize_tickets(other_report)
    assert other_report[0].assignee == "Person 1"
    assert "Alice Smith" in other_report[0].title  # Unknown names are outside documented coverage.


@pytest.mark.parametrize("text", ["Host 192.0.2.1.", "Host 2001:db8::1."])
def test_ip_sentence_punctuation(text):
    assert strip_pii(text) == "Host [REDACTED_IP]."


def test_card_adjacent_to_unrelated_numbers():
    assert "4111-1111-1111-1111" not in strip_pii("Person 1 4111-1111-1111-1111")
    assert "4111 1111 1111 1111" not in strip_pii("4111 1111 1111 1111 2 items")
