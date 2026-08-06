import pytest
from app.core.ssrf_guard import assert_safe_url, UnsafeURLError


def test_rejects_loopback():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://127.0.0.1:8000/", allow_private=False)


def test_rejects_loopback_even_when_private_allowed():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://localhost:11434/", allow_private=True)


def test_rejects_metadata_ip():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://169.254.169.254/latest/meta-data/", allow_private=True)


def test_rejects_private_by_default():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://10.0.0.5/", allow_private=False)


def test_allows_private_when_explicitly_permitted():
    assert_safe_url("http://10.0.0.5/", allow_private=True)


def test_rejects_bad_scheme():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("file:///etc/passwd", allow_private=True)


def test_allows_public_host():
    assert_safe_url("https://example.com/rest/api/3/myself", allow_private=False)
