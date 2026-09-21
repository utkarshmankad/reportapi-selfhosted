import httpx
import pytest
import respx

from app.connectors.jira import JiraConnector


@pytest.fixture
def mock_jira_search_response():
    return {
        "isLast": True,
        "issues": [
            {
                "key": "PROJ-123",
                "fields": {
                    "summary": "Fix login bug",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Users cannot log in on Safari"}
                                ],
                            }
                        ],
                    },
                    "status": {"name": "In Progress"},
                    "assignee": {"displayName": "Jane Doe"},
                    "priority": {"name": "High"},
                    "labels": ["bug", "urgent"],
                    "created": "2026-05-01T10:00:00.000+0000",
                    "updated": "2026-05-02T10:00:00.000+0000",
                    "sprint": [{"name": "Sprint 14"}],
                },
            }
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_normalises_tickets(mock_jira_search_response, monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search/jql").mock(
        return_value=httpx.Response(200, json=mock_jira_search_response)
    )

    connector = JiraConnector()
    result = await connector.fetch({"board_id": "PROJ"})
    tickets = result.tickets

    assert len(tickets) == 1
    assert tickets[0].id == "PROJ-123"
    assert tickets[0].status == "in_progress"
    assert tickets[0].description == "Users cannot log in on Safari"
    assert tickets[0].sprint == "Sprint 14"
