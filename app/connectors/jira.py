"""Jira connector."""

from app.config import Settings, settings
from app.connectors.base import Connector, FetchResult
from app.core.ssrf_guard import safe_client
from app.models.report import validate_connector_scope
from app.models.ticket import Ticket

STATUS_MAP = {
    "To Do": "todo",
    "In Progress": "in_progress",
    "Done": "done",
    "Blocked": "blocked",
}

PAGE_SIZE = 100
MAX_PAGES = 50
MAX_RECORDS = 5000


class JiraConnector(Connector):
    def __init__(self, config: Settings | None = None):
        config = config or settings
        if not config.jira_url or not config.jira_email or not config.jira_api_token:
            raise ValueError(
                "Jira credentials not configured. Set JIRA_URL, JIRA_EMAIL, "
                "and JIRA_API_TOKEN in your environment."
            )
        self.base_url = config.jira_url.rstrip("/")
        self.auth = (config.jira_email, config.jira_api_token)

    async def authenticate(self) -> bool:
        async with safe_client(self.base_url, "jira", auth=self.auth, timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/rest/api/3/myself")
            return response.status_code == 200

    async def fetch(self, config: dict) -> FetchResult:
        board_id = config.get("board_id")
        sprint_id = config.get("sprint_id")
        validate_connector_scope("jira", board_id, sprint_id)

        if sprint_id:
            jql = f"sprint = {sprint_id}"
        elif board_id:
            jql = f"project = {board_id}"
        else:
            raise ValueError("config must include either 'board_id' or 'sprint_id'")

        tickets: list[Ticket] = []
        truncated = False
        truncation_reason: str | None = None
        start_at = 0
        seen_start_ats: set[int] = set()

        async with safe_client(self.base_url, "jira", auth=self.auth, timeout=15.0) as client:
            for page in range(MAX_PAGES):
                if start_at in seen_start_ats:
                    truncated = True
                    truncation_reason = "Jira returned a repeated pagination cursor"
                    break
                seen_start_ats.add(start_at)

                try:
                    response = await client.get(
                        f"{self.base_url}/rest/api/3/search",
                        params={
                            "jql": jql,
                            "startAt": start_at,
                            "maxResults": PAGE_SIZE,
                            "fields": "summary,description,status,assignee,priority,"
                            "labels,created,updated,sprint",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    if page == 0:
                        raise
                    truncated = True
                    truncation_reason = f"Jira page fetch failed at offset {start_at}"
                    break

                issues = data.get("issues", [])
                for issue in issues:
                    fields = issue["fields"]
                    raw_status = fields["status"]["name"]

                    tickets.append(
                        Ticket(
                            id=issue["key"],
                            title=fields.get("summary", ""),
                            description=self._extract_description(fields.get("description")),
                            status=STATUS_MAP.get(raw_status, "todo"),
                            assignee=(fields.get("assignee") or {}).get("displayName"),
                            priority=(fields.get("priority") or {}).get("name"),
                            labels=fields.get("labels", []),
                            created_at=fields["created"],
                            updated_at=fields["updated"],
                            sprint=self._extract_sprint_name(fields.get("sprint")),
                            url=f"{self.base_url}/browse/{issue['key']}",
                        )
                    )

                total = data.get("total")
                start_at += len(issues)
                if len(tickets) >= MAX_RECORDS:
                    truncated = total is not None and start_at < total
                    if truncated:
                        truncation_reason = f"Reached the {MAX_RECORDS}-record fetch limit"
                    break
                if not issues:
                    break
                if total is not None and start_at >= total:
                    break
            else:
                # Exhausted MAX_PAGES without the source signaling completion.
                truncated = True
                truncation_reason = f"Reached the {MAX_PAGES}-page fetch limit"

        return FetchResult(
            tickets=tickets, truncated=truncated, truncation_reason=truncation_reason
        )

    @staticmethod
    def _extract_description(description_field) -> str:
        if not description_field:
            return ""
        if isinstance(description_field, str):
            return description_field
        # Jira Cloud returns Atlassian Document Format (ADF) — extract plain text
        text_parts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(description_field)
        return " ".join(text_parts)

    @staticmethod
    def _extract_sprint_name(sprint_field) -> str | None:
        if not sprint_field:
            return None
        if isinstance(sprint_field, list) and sprint_field:
            return sprint_field[0].get("name")
        return None
