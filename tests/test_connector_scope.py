"""Typed connector scope validation: shared between manual reports and schedules."""

import pytest

from app.connectors.asana import AsanaConnector
from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector
from app.models.report import GenerateReportRequest, validate_connector_scope
from app.models.schedule import CreateScheduleRequest


@pytest.mark.parametrize(
    "connector,board_id,sprint_id",
    [
        ("jira", "PROJ", None),
        ("jira", None, "42"),
        ("jira", "D", None),
        ("asana", "1200", None),
        ("asana", None, "555"),
        ("github", "acme/widgets", None),
        ("github", "acme/widgets", "3"),
    ],
)
def test_valid_scopes_accepted(connector, board_id, sprint_id):
    validate_connector_scope(connector, board_id, sprint_id)


@pytest.mark.parametrize(
    "connector,board_id,sprint_id",
    [
        # Jira JQL injection attempts
        ("jira", "PROJ' OR 1=1--", None),
        ("jira", None, "1 OR sprint IS NOT EMPTY"),
        ("jira", "PROJ; DROP", None),
        # Asana/GitHub URL path injection attempts
        ("asana", "../../users/me", None),
        ("asana", None, "1200/tasks"),
        ("github", "acme/widgets/../../user", None),
        ("github", "acme", None),  # missing "/repo" half
        ("github", "acme/widgets", "not-a-number"),
        # unsupported connector
        ("bitbucket", "PROJ", None),
    ],
)
def test_malformed_or_injection_scopes_rejected(connector, board_id, sprint_id):
    with pytest.raises(ValueError):
        validate_connector_scope(connector, board_id, sprint_id)


def test_generate_report_request_rejects_jql_injection():
    with pytest.raises(ValueError):
        GenerateReportRequest(connector="jira", board_id="PROJ' OR 1=1--")


def test_schedule_request_uses_same_validation_as_report_request():
    with pytest.raises(ValueError):
        CreateScheduleRequest(
            connector="jira",
            board_id="PROJ' OR 1=1--",
            cron_expression="0 9 * * 1",
        )


@pytest.mark.asyncio
async def test_jira_connector_rejects_injection_before_request(monkeypatch):
    connector = JiraConnector.__new__(JiraConnector)
    connector.base_url = "https://example.atlassian.net"
    connector.auth = ("user", "token")
    with pytest.raises(ValueError):
        await connector.fetch({"board_id": "PROJ' OR 1=1--"})


@pytest.mark.asyncio
async def test_asana_connector_rejects_injection_before_request(monkeypatch):
    connector = AsanaConnector.__new__(AsanaConnector)
    connector.headers = {}
    with pytest.raises(ValueError):
        await connector.fetch({"board_id": "1200/../users/me"})


@pytest.mark.asyncio
async def test_github_connector_rejects_injection_before_request(monkeypatch):
    connector = GitHubConnector.__new__(GitHubConnector)
    connector.headers = {}
    with pytest.raises(ValueError):
        await connector.fetch({"board_id": "acme/widgets/../../user"})


def test_period_start_after_period_end_rejected():
    from datetime import datetime, timezone

    with pytest.raises(ValueError):
        GenerateReportRequest(
            connector="jira",
            board_id="PROJ",
            period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_period_start_before_period_end_accepted():
    from datetime import datetime, timezone

    request = GenerateReportRequest(
        connector="jira",
        board_id="PROJ",
        period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert request.period_start is not None
