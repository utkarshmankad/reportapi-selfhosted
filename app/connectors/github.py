"""GitHub Issues connector.

GitHub has no native board/sprint split either — issues live in a repo,
optionally grouped into a milestone. `board_id` maps to `owner/repo`,
`sprint_id` (when given) maps to a milestone number and narrows the fetch
to that milestone.
"""

import httpx

from app.config import Settings, settings
from app.connectors.base import Connector, FetchResult
from app.models.report import validate_connector_scope
from app.models.ticket import Ticket

API_BASE = "https://api.github.com"

PAGE_SIZE = 100
MAX_PAGES = 50
MAX_RECORDS = 5000

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
    def __init__(self, config: Settings | None = None):
        config = config or settings
        if not config.github_pat:
            raise ValueError(
                "GitHub credentials not configured. Set GITHUB_PAT in your environment."
            )
        self.headers = {
            "Authorization": f"Bearer {config.github_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def authenticate(self) -> bool:
        async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
            response = await client.get(f"{API_BASE}/user")
            return response.status_code == 200

    async def fetch(self, config: dict) -> FetchResult:
        repo = config.get("board_id")
        milestone = config.get("sprint_id")
        validate_connector_scope("github", repo, milestone)
        if not repo:
            raise ValueError("config must include 'board_id' as 'owner/repo'")

        tickets: list[Ticket] = []
        truncated = False
        truncation_reason: str | None = None

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            for page in range(1, MAX_PAGES + 1):
                params = {"state": "all", "per_page": PAGE_SIZE, "page": page}
                if milestone:
                    params["milestone"] = milestone

                try:
                    response = await client.get(f"{API_BASE}/repos/{repo}/issues", params=params)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    if page == 1:
                        raise
                    truncated = True
                    truncation_reason = f"GitHub page fetch failed at page {page}"
                    break

                # Pull requests never consume the issue record limit — they're
                # filtered before counting toward MAX_RECORDS or truncation.
                issues_only = [issue for issue in data if "pull_request" not in issue]

                for issue in issues_only:
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

                is_last_page = len(data) < PAGE_SIZE
                if len(tickets) >= MAX_RECORDS:
                    truncated = not is_last_page
                    if truncated:
                        truncation_reason = f"Reached the {MAX_RECORDS}-record fetch limit"
                    break
                if is_last_page:
                    break
            else:
                truncated = True
                truncation_reason = f"Reached the {MAX_PAGES}-page fetch limit"

        return FetchResult(
            tickets=tickets, truncated=truncated, truncation_reason=truncation_reason
        )

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
