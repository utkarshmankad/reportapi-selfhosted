"""Bounded pagination, repeated-cursor detection and later-page failure handling."""

import httpx
import pytest
import respx

from app.connectors.asana import AsanaConnector
from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector


def _jira_issue(n):
    return {
        "key": f"PROJ-{n}",
        "fields": {
            "summary": f"issue {n}",
            "description": None,
            "status": {"name": "To Do"},
            "assignee": None,
            "priority": None,
            "labels": [],
            "created": "2026-05-01T10:00:00.000+0000",
            "updated": "2026-05-02T10:00:00.000+0000",
            "sprint": None,
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_jira_paginates_across_multiple_pages(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    def responder(request):
        start_at = int(request.url.params.get("nextPageToken", "0"))
        remaining = 250 - start_at
        count = min(100, remaining)
        page = [_jira_issue(start_at + i) for i in range(count)]
        is_last = start_at + count >= 250
        return httpx.Response(
            200,
            json={
                "isLast": is_last,
                "nextPageToken": None if is_last else str(start_at + count),
                "issues": page,
            },
        )

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(side_effect=responder)

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert len(result.tickets) == 250
    assert result.truncated is False


@pytest.mark.asyncio
@respx.mock
async def test_jira_marks_truncated_on_page_limit(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    def responder(request):
        start_at = int(request.url.params.get("nextPageToken", "0"))
        return httpx.Response(
            200,
            json={
                "isLast": False,
                "nextPageToken": str(start_at + 100),
                "issues": [_jira_issue(start_at + i) for i in range(100)],
            },
        )

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(side_effect=responder)

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert result.truncated is True
    assert result.truncation_reason is not None
    assert len(result.tickets) > 0


@pytest.mark.asyncio
@respx.mock
async def test_jira_later_page_failure_keeps_partial_results(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200,
            json={
                "isLast": False,
                "nextPageToken": "100",
                "issues": [_jira_issue(i) for i in range(100)],
            },
        )

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(side_effect=responder)

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert result.truncated is True
    assert len(result.tickets) == 100


@pytest.mark.asyncio
@respx.mock
async def test_jira_first_page_failure_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    connector = JiraConnector()
    with pytest.raises(Exception):
        await connector.fetch({"board_id": "PROJ"})


@pytest.mark.asyncio
@respx.mock
async def test_asana_follows_next_page_offset(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    def responder(request):
        offset = request.url.params.get("offset")
        if not offset:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "gid": "1",
                            "name": "t1",
                            "created_at": "2026-05-01T10:00:00Z",
                            "modified_at": "2026-05-02T10:00:00Z",
                        }
                    ],
                    "next_page": {"offset": "cursor-2"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "2",
                        "name": "t2",
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                    }
                ],
                "next_page": None,
            },
        )

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(side_effect=responder)

    connector = AsanaConnector()
    result = await connector.fetch({"board_id": "1200"})

    assert [t.id for t in result.tickets] == ["1", "2"]
    assert result.truncated is False


@pytest.mark.asyncio
@respx.mock
async def test_asana_detects_repeated_cursor(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "1",
                        "name": "t1",
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                    }
                ],
                "next_page": {"offset": "same-cursor"},
            },
        )
    )

    connector = AsanaConnector()
    result = await connector.fetch({"board_id": "1200"})

    assert result.truncated is True
    assert "cursor" in result.truncation_reason


@pytest.mark.asyncio
@respx.mock
async def test_asana_later_page_failure_keeps_partial_results(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "1",
                        "name": "t1",
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                    }
                ],
                "next_page": {"offset": "cursor-2"},
            },
        )

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(side_effect=responder)

    connector = AsanaConnector()
    result = await connector.fetch({"board_id": "1200"})

    assert result.truncated is True
    assert len(result.tickets) == 1


@pytest.mark.asyncio
@respx.mock
async def test_asana_first_page_failure_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    connector = AsanaConnector()
    with pytest.raises(Exception):
        await connector.fetch({"board_id": "1200"})


@pytest.mark.asyncio
@respx.mock
async def test_github_later_page_failure_keeps_partial_results(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "boom"})
        issue = {
            "number": 1,
            "title": "issue",
            "body": "",
            "state": "open",
            "assignee": None,
            "labels": [],
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-02T10:00:00Z",
            "milestone": None,
        }
        return httpx.Response(200, json=[issue] * 100)

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(side_effect=responder)

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})

    assert result.truncated is True
    assert len(result.tickets) == 100


@pytest.mark.asyncio
@respx.mock
async def test_github_first_page_failure_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    connector = GitHubConnector()
    with pytest.raises(Exception):
        await connector.fetch({"board_id": "acme/widgets"})


@pytest.mark.asyncio
@respx.mock
async def test_github_marks_truncated_on_page_limit(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    issue_template = {
        "title": "issue",
        "body": "",
        "state": "open",
        "assignee": None,
        "labels": [],
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "milestone": None,
    }

    def responder(request):
        page = int(request.url.params["page"])
        return httpx.Response(
            200, json=[{**issue_template, "number": page * 100 + i} for i in range(100)]
        )

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(side_effect=responder)

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})

    assert result.truncated is True
    assert result.truncation_reason is not None


@pytest.mark.asyncio
@respx.mock
async def test_jira_truncates_mid_page_at_record_limit(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    def responder(request):
        start_at = int(request.url.params.get("nextPageToken", "0"))
        return httpx.Response(
            200,
            json={
                "isLast": False,
                "nextPageToken": str(start_at + 100),
                "issues": [_jira_issue(start_at + i) for i in range(100)],
            },
        )

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(side_effect=responder)

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert result.truncated is True
    assert len(result.tickets) == 5000


@pytest.mark.asyncio
@respx.mock
async def test_github_paginates_and_excludes_prs_from_limit(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    def responder(request):
        page = int(request.url.params["page"])
        if page == 1:
            issues = [
                {
                    "number": 1,
                    "title": "pr",
                    "body": "",
                    "state": "open",
                    "pull_request": {},
                    "labels": [],
                    "created_at": "x",
                    "updated_at": "y",
                    "milestone": None,
                }
            ] * 100
            return httpx.Response(200, json=issues)
        return httpx.Response(200, json=[])

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(side_effect=responder)

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})

    assert result.tickets == []
    assert result.truncated is False
