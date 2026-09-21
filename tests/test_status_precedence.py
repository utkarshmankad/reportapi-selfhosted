"""Closed/completed source state must be authoritative over label/section hints (S2-02)."""

import httpx
import pytest
import respx

from app.connectors.asana import AsanaConnector
from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector


@pytest.mark.asyncio
@respx.mock
async def test_jira_falls_back_to_status_category_for_custom_workflow(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(
        return_value=httpx.Response(
            200,
            json={
                "isLast": True,
                "issues": [
                    {
                        "key": "PROJ-1",
                        "fields": {
                            "summary": "s",
                            "description": None,
                            "status": {
                                "name": "Awaiting QA",
                                "statusCategory": {"key": "indeterminate"},
                            },
                            "assignee": None,
                            "priority": None,
                            "labels": [],
                            "created": "2026-05-01T10:00:00.000+0000",
                            "updated": "2026-05-02T10:00:00.000+0000",
                            "sprint": None,
                        },
                    }
                ],
            },
        )
    )

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert result.tickets[0].status == "in_progress"


@pytest.mark.asyncio
@respx.mock
async def test_jira_custom_done_category_maps_to_done(monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(
        return_value=httpx.Response(
            200,
            json={
                "isLast": True,
                "issues": [
                    {
                        "key": "PROJ-2",
                        "fields": {
                            "summary": "s",
                            "description": None,
                            "status": {
                                "name": "Shipped",
                                "statusCategory": {"key": "done"},
                            },
                            "assignee": None,
                            "priority": None,
                            "labels": [],
                            "created": "2026-05-01T10:00:00.000+0000",
                            "updated": "2026-05-02T10:00:00.000+0000",
                            "sprint": None,
                        },
                    }
                ],
            },
        )
    )

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})

    assert result.tickets[0].status == "done"


@pytest.mark.asyncio
@respx.mock
async def test_asana_completed_flag_overrides_stale_section(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "1",
                        "name": "t",
                        "completed": True,
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                        "memberships": [{"section": {"name": "In Progress"}}],
                    }
                ]
            },
        )
    )

    connector = AsanaConnector()
    result = await connector.fetch({"board_id": "1200"})

    assert result.tickets[0].status == "done"


@pytest.mark.asyncio
@respx.mock
async def test_asana_matches_membership_to_queried_project(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "1",
                        "name": "t",
                        "completed": False,
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                        "memberships": [
                            {
                                "section": {"name": "Done", "gid": "s1"},
                                "project": {"gid": "9999"},
                            },
                            {
                                "section": {"name": "In Progress", "gid": "s2"},
                                "project": {"gid": "1200"},
                            },
                        ],
                    }
                ]
            },
        )
    )

    connector = AsanaConnector()
    result = await connector.fetch({"board_id": "1200"})

    assert result.tickets[0].sprint == "In Progress"
    assert result.tickets[0].status == "in_progress"


@pytest.mark.asyncio
@respx.mock
async def test_github_closed_state_overrides_stale_blocked_label(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "t",
                    "body": "",
                    "state": "closed",
                    "assignee": None,
                    "labels": [{"name": "blocked"}],
                    "created_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-02T10:00:00Z",
                    "milestone": None,
                }
            ],
        )
    )

    connector = GitHubConnector()
    result = await connector.fetch({"board_id": "acme/widgets"})

    assert result.tickets[0].status == "done"


@pytest.mark.asyncio
@respx.mock
async def test_github_assigned_means_in_progress_can_be_disabled(monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "t",
                    "body": "",
                    "state": "open",
                    "assignee": {"login": "janedoe"},
                    "labels": [],
                    "created_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-02T10:00:00Z",
                    "milestone": None,
                }
            ],
        )
    )

    connector = GitHubConnector()
    result = await connector.fetch(
        {"board_id": "acme/widgets", "assigned_means_in_progress": False}
    )

    assert result.tickets[0].status == "todo"
