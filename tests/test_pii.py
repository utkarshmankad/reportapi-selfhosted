from app.core.pii import luhn_check, strip_pii


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
