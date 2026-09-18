import httpx
import pytest
import respx

from app.connectors.github import GitHubConnector


@pytest.fixture
def mock_github_issues_response():
    return [
        {
            "number": 42,
            "title": "Fix login bug",
            "body": "Users cannot log in on Safari",
            "state": "open",
            "assignee": {"login": "janedoe"},
            "labels": [{"name": "bug"}, {"name": "priority: high"}],
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-02T10:00:00Z",
            "milestone": {"title": "v1.2"},
            "html_url": "https://github.com/acme/widgets/issues/42",
        },
        {
            "number": 43,
            "title": "A pull request, not an issue",
            "body": "",
            "state": "open",
            "pull_request": {"url": "https://api.github.com/repos/acme/widgets/pulls/43"},
            "labels": [],
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-02T10:00:00Z",
            "html_url": "https://github.com/acme/widgets/pull/43",
        },
    ]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_normalises_issues_and_skips_prs(mock_github_issues_response, monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(200, json=mock_github_issues_response)
    )

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})
    tickets = result.tickets

    assert len(tickets) == 1
    assert tickets[0].id == "42"
    assert tickets[0].status == "in_progress"
    assert tickets[0].description == "Users cannot log in on Safari"
    assert tickets[0].sprint == "v1.2"
    assert tickets[0].priority == "priority: high"
    assert tickets[0].assignee == "janedoe"
    assert tickets[0].labels == ["bug", "priority: high"]


@pytest.mark.asyncio
@respx.mock
async def test_closed_issue_maps_to_done(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 44,
                    "title": "Ship release notes",
                    "body": None,
                    "state": "closed",
                    "assignee": None,
                    "labels": [],
                    "created_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-02T10:00:00Z",
                    "milestone": None,
                    "html_url": "https://github.com/acme/widgets/issues/44",
                }
            ],
        )
    )

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})
    tickets = result.tickets

    assert tickets[0].status == "done"
    assert tickets[0].sprint is None
    assert tickets[0].priority is None


@pytest.mark.asyncio
@respx.mock
async def test_status_label_hint_overrides_open_state(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 45,
                    "title": "Investigate flaky test",
                    "body": "",
                    "state": "open",
                    "assignee": None,
                    "labels": [{"name": "in progress"}],
                    "created_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-02T10:00:00Z",
                    "milestone": None,
                    "html_url": "https://github.com/acme/widgets/issues/45",
                }
            ],
        )
    )

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})
    tickets = result.tickets

    assert tickets[0].status == "in_progress"


@pytest.mark.asyncio
@respx.mock
async def test_unassigned_open_issue_maps_to_todo(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 46,
                    "title": "Untouched backlog item",
                    "body": "",
                    "state": "open",
                    "assignee": None,
                    "labels": [],
                    "created_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-02T10:00:00Z",
                    "milestone": None,
                    "html_url": "https://github.com/acme/widgets/issues/46",
                }
            ],
        )
    )

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})
    tickets = result.tickets

    assert tickets[0].status == "todo"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_filters_by_milestone(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    route = respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(200, json=[])
    )

    connector = GitHubConnector()
    await connector.fetch({"board_id": "acme/widgets", "sprint_id": "3"})

    assert route.calls.last.request.url.params["milestone"] == "3"


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", None)

    with pytest.raises(ValueError):
        GitHubConnector()


@pytest.mark.asyncio
async def test_fetch_without_repo_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    connector = GitHubConnector()
    with pytest.raises(ValueError):
        await connector.fetch({})
