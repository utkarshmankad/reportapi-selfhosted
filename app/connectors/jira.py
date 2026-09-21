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

# Jira's built-in status category (new/indeterminate/done) is authoritative
# for workflows with custom status names that aren't in STATUS_MAP above —
# it reflects where the workflow actually places the ticket, not a guess.
STATUS_CATEGORY_MAP = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
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
        next_page_token: str | None = None
        seen_page_tokens: set[str] = set()

        async with safe_client(self.base_url, "jira", auth=self.auth, timeout=15.0) as client:
            for page in range(MAX_PAGES):
                try:
                    params = {
                        "jql": jql,
                        "maxResults": PAGE_SIZE,
                        "fields": "summary,description,status,assignee,priority,"
                        "labels,created,updated,sprint",
                    }
                    if next_page_token:
                        params["nextPageToken"] = next_page_token
                    response = await client.get(
                        f"{self.base_url}/rest/api/3/search/jql",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    if page == 0:
                        raise
                    truncated = True
                    truncation_reason = "Jira page fetch failed"
                    break

                issues = data.get("issues", [])
                for issue in issues:
                    fields = issue["fields"]
                    tickets.append(
                        Ticket(
                            id=issue["key"],
                            title=fields.get("summary", ""),
                            description=self._extract_description(fields.get("description")),
                            status=self._resolve_status(fields["status"]),
                            assignee=(fields.get("assignee") or {}).get("displayName"),
                            priority=(fields.get("priority") or {}).get("name"),
                            labels=fields.get("labels", []),
                            created_at=fields["created"],
                            updated_at=fields["updated"],
                            sprint=self._extract_sprint_name(fields.get("sprint")),
                            url=f"{self.base_url}/browse/{issue['key']}",
                        )
                    )

                if len(tickets) >= MAX_RECORDS:
                    truncated = not data.get("isLast", False)
                    if truncated:
                        truncation_reason = f"Reached the {MAX_RECORDS}-record fetch limit"
                    break
                if not issues:
                    break
                if data.get("isLast", False):
                    break

                candidate = data.get("nextPageToken")
                if not candidate:
                    truncated = True
                    truncation_reason = "Jira did not return a next-page token"
                    break
                if candidate in seen_page_tokens:
                    truncated = True
                    truncation_reason = "Jira returned a repeated pagination cursor"
                    break
                seen_page_tokens.add(candidate)
                next_page_token = candidate
            else:
                # Exhausted MAX_PAGES without the source signaling completion.
                truncated = True
                truncation_reason = f"Reached the {MAX_PAGES}-page fetch limit"

        return FetchResult(
            tickets=tickets, truncated=truncated, truncation_reason=truncation_reason
        )

    @staticmethod
    def _resolve_status(status_field: dict) -> str:
        name = status_field.get("name")
        if name in STATUS_MAP:
            return STATUS_MAP[name]
        category_key = (status_field.get("statusCategory") or {}).get("key")
        return STATUS_CATEGORY_MAP.get(category_key, "todo")

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
