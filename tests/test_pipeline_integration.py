"""Full pipeline: fetch -> pagination -> filtering -> budgeting -> provider -> persistence.

Exercises generate_report() end-to-end through the real connector HTTP layer
(mocked with respx — no live credentials or DNS) for every connector, plus
the failure modes that must not be swallowed silently: empty input, a
partial-page failure, an inaccurate/stale count, and a persistence failure.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from app.core.report_service import ReportGenerationError, generate_report


@pytest.fixture
def database():
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def stub_llm(monkeypatch):
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)
    return llm


def _jira_issue(n, updated="2026-05-02T10:00:00.000+0000"):
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
            "updated": updated,
            "sprint": None,
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_jira_full_pipeline_persists_paginated_result(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    def responder(request):
        start_at = int(request.url.params["startAt"])
        remaining = 150 - start_at
        count = min(100, remaining)
        return httpx.Response(
            200, json={"total": 150, "issues": [_jira_issue(start_at + i) for i in range(count)]}
        )

    respx.get("https://test.atlassian.net/rest/api/3/search").mock(side_effect=responder)

    report, count = await generate_report(database, "jira", "PROJ", None)

    assert count == 150
    assert report.status == "complete"
    assert report.is_truncated is False
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_jira_full_pipeline_empty_result_rejected(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(200, json={"total": 0, "issues": []})
    )

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "jira", "PROJ", None)
    assert error.value.status_code == 422
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
@respx.mock
async def test_jira_full_pipeline_partial_page_failure_still_persists(
    database, stub_llm, monkeypatch
):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200, json={"total": 250, "issues": [_jira_issue(i) for i in range(100)]}
        )

    respx.get("https://test.atlassian.net/rest/api/3/search").mock(side_effect=responder)

    report, count = await generate_report(database, "jira", "PROJ", None)

    assert count == 100
    assert report.status == "partial"
    assert report.is_truncated is True
    assert "Jira page fetch failed" in report.truncation_reason
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_jira_full_pipeline_persistence_failure_raises(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    respx.get("https://test.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(200, json={"total": 1, "issues": [_jira_issue(1)]})
    )
    database.commit.side_effect = RuntimeError("db down")

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "jira", "PROJ", None)
    assert error.value.status_code == 500
    database.rollback.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_asana_full_pipeline_persists_paginated_result(database, stub_llm, monkeypatch):
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
                            "completed": False,
                            "created_at": "2026-05-01T10:00:00Z",
                            "modified_at": "2026-05-02T10:00:00Z",
                        }
                    ],
                    "next_page": {"offset": "p2"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "gid": "2",
                        "name": "t2",
                        "completed": True,
                        "created_at": "2026-05-01T10:00:00Z",
                        "modified_at": "2026-05-02T10:00:00Z",
                    }
                ],
                "next_page": None,
            },
        )

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(side_effect=responder)

    report, count = await generate_report(database, "asana", "1200", None)

    assert count == 2
    assert report.status == "complete"
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_asana_full_pipeline_empty_result_rejected(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.asana_pat", "fake-pat")

    respx.get("https://app.asana.com/api/1.0/projects/1200/tasks").mock(
        return_value=httpx.Response(200, json={"data": [], "next_page": None})
    )

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "asana", "1200", None)
    assert error.value.status_code == 422
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
@respx.mock
async def test_github_full_pipeline_persists_result_excluding_prs(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    issue = {
        "number": 1,
        "title": "Fix it",
        "body": "",
        "state": "open",
        "assignee": None,
        "labels": [],
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "milestone": None,
    }
    pr = {
        "number": 2,
        "title": "A PR",
        "body": "",
        "state": "open",
        "pull_request": {},
        "labels": [],
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
    }

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(200, json=[issue, pr])
    )

    report, count = await generate_report(database, "github", "acme/widgets", None)

    assert count == 1
    assert report.status == "complete"
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_github_full_pipeline_empty_result_rejected(database, stub_llm, monkeypatch):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=httpx.Response(200, json=[])
    )

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "github", "acme/widgets", None)
    assert error.value.status_code == 422
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
@respx.mock
async def test_github_full_pipeline_partial_page_failure_still_persists(
    database, stub_llm, monkeypatch
):
    monkeypatch.setattr("app.config.settings.github_pat", "fake-pat")

    calls = {"n": 0}
    issue_template = {
        "title": "t",
        "body": "",
        "state": "open",
        "assignee": None,
        "labels": [],
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "milestone": None,
    }

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=[{**issue_template, "number": i} for i in range(100)])

    respx.get("https://api.github.com/repos/acme/widgets/issues").mock(side_effect=responder)

    report, count = await generate_report(database, "github", "acme/widgets", None)

    assert count == 100
    assert report.status == "partial"
    assert report.is_truncated is True
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline_count_reflects_dedup_not_raw_fetch_count(
    database, stub_llm, monkeypatch
):
    """A stale/duplicate record from the source must not inflate the reported count."""
    monkeypatch.setattr("app.config.settings.jira_url", "https://test.atlassian.net")
    monkeypatch.setattr("app.config.settings.jira_email", "test@test.com")
    monkeypatch.setattr("app.config.settings.jira_api_token", "fake-token")

    duplicate_issue = _jira_issue(1)

    respx.get("https://test.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(
            200, json={"total": 2, "issues": [duplicate_issue, duplicate_issue]}
        )
    )

    report, count = await generate_report(database, "jira", "PROJ", None)

    assert count == 1
    assert report.status == "complete"
