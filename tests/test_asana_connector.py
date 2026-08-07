import pytest
import respx
import httpx
from app.connectors.asana import AsanaConnector


@pytest.fixture
def mock_asana_tasks_response():
    return {
        "data": [
            {
                "gid": "1201",
                "name": "Fix login bug",
                "notes": "Users cannot log in on Safari",
                "completed": False,
                "assignee": {"name": "Jane Doe"},
                "tags": [{"name": "bug"}, {"name": "urgent"}],
                "created_at": "2026-05-01T10:00:00.000Z",
                "modified_at": "2026-05-02T10:00:00.000Z",
                "memberships": [{"section": {"name": "In Progress"}}],
                "permalink_url": "https://app.asana.com/0/1200/1201",
                "custom_fields": [{"name": "Priority", "display_value": "High"}],
            }
        ]
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_normalises_tasks(mock_asana_tasks_response, monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(200, json=mock_asana_tasks_response)
    )

    connector = AsanaConnector()
    tickets = await connector.fetch({"board_id": "1200"})

    assert len(tickets) == 1
    assert tickets[0].id == "1201"
    assert tickets[0].status == "in_progress"
    assert tickets[0].description == "Users cannot log in on Safari"
    assert tickets[0].sprint == "In Progress"
    assert tickets[0].priority == "High"
    assert tickets[0].labels == ["bug", "urgent"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_falls_back_to_completed_flag(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(200, json={"data": [{
            "gid": "1202",
            "name": "Ship release notes",
            "notes": "",
            "completed": True,
            "assignee": None,
            "tags": [],
            "created_at": "2026-05-01T10:00:00.000Z",
            "modified_at": "2026-05-02T10:00:00.000Z",
            "memberships": [],
            "permalink_url": "https://app.asana.com/0/1200/1202",
            "custom_fields": [],
        }]})
    )

    connector = AsanaConnector()
    tickets = await connector.fetch({"board_id": "1200"})

    assert tickets[0].status == "done"
    assert tickets[0].sprint is None
    assert tickets[0].priority is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_by_section_uses_section_endpoint(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/sections/555/tasks").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    connector = AsanaConnector()
    tickets = await connector.fetch({"sprint_id": "555"})

    assert tickets == []


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", None)

    with pytest.raises(ValueError):
        AsanaConnector()


@pytest.mark.asyncio
async def test_fetch_without_project_or_section_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    connector = AsanaConnector()
    with pytest.raises(ValueError):
        await connector.fetch({})
