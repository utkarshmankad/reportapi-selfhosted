"""GitHub Issues connector.

GitHub has no native board/sprint split either — issues live in a repo,
optionally grouped into a milestone. `board_id` maps to `owner/repo`,
`sprint_id` (when given) maps to a milestone number and narrows the fetch
to that milestone.
"""

import httpx

from app.config import settings
from app.connectors.base import Connector
from app.models.ticket import Ticket

API_BASE = "https://api.github.com"

# GitHub issues only have an open/closed state natively. Status is inferred
# from labels, falling back to open/closed.
LABEL_STATUS_HINTS = {
    "in progress": "in_progress",
    "in-progress": "in_progress",
    "wip": "in_progress",
    "blocked": "blocked",
    "on hold": "blocked",
}

PRIORITY_LABEL_PREFIXES = ("priority:", "priority/", "p0", "p1", "p2", "p3")


class GitHubConnector(Connector):
    def __init__(self):
        if not settings.github_pat:
            raise ValueError(
                "GitHub credentials not configured. Set GITHUB_PAT in your environment."
            )
        self.headers = {
            "Authorization": f"Bearer {settings.github_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def authenticate(self) -> bool:
        async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
            response = await client.get(f"{API_BASE}/user")
            return response.status_code == 200

    async def fetch(self, config: dict) -> list[Ticket]:
        repo = config.get("board_id")
        milestone = config.get("sprint_id")

        if not repo:
            raise ValueError("config must include 'board_id' as 'owner/repo'")

        params = {"state": "all", "per_page": 100}
        if milestone:
            params["milestone"] = milestone

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            response = await client.get(f"{API_BASE}/repos/{repo}/issues", params=params)
            response.raise_for_status()
            data = response.json()

        tickets: list[Ticket] = []
        for issue in data:
            # The issues endpoint also returns pull requests; skip them.
            if "pull_request" in issue:
                continue

            labels = [
                label.get("name") if isinstance(label, dict) else label
                for label in issue.get("labels", [])
            ]
            labels = [label for label in labels if label]

            tickets.append(
                Ticket(
                    id=str(issue["number"]),
                    title=issue.get("title", ""),
                    description=issue.get("body") or "",
                    status=self._resolve_status(issue, labels),
                    assignee=(issue.get("assignee") or {}).get("login"),
                    priority=self._extract_priority(labels),
                    labels=labels,
                    created_at=issue["created_at"],
                    updated_at=issue["updated_at"],
                    sprint=(issue.get("milestone") or {}).get("title"),
                    url=issue.get("html_url", ""),
                )
            )

        return tickets

    @staticmethod
    def _resolve_status(issue: dict, labels: list[str]) -> str:
        for label in labels:
            hint = LABEL_STATUS_HINTS.get(label.strip().lower())
            if hint:
                return hint
        if issue.get("state") == "closed":
            return "done"
        # GitHub issues have no native "in progress" state. An open issue
        # with an assignee and no explicit status label is being worked,
        # not sitting untouched — treat it as in_progress rather than
        # lumping active work into "todo".
        return "in_progress" if issue.get("assignee") else "todo"

    @staticmethod
    def _extract_priority(labels: list[str]) -> str | None:
        for label in labels:
            lowered = label.strip().lower()
            if lowered.startswith(PRIORITY_LABEL_PREFIXES):
                return label
        return None
