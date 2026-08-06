"""Jira connector."""
import httpx
from app.connectors.base import Connector
from app.models.ticket import Ticket
from app.config import settings

STATUS_MAP = {
    "To Do": "todo",
    "In Progress": "in_progress",
    "Done": "done",
    "Blocked": "blocked",
}


class JiraConnector(Connector):
    def __init__(self):
        if not settings.jira_url or not settings.jira_email or not settings.jira_api_token:
            raise ValueError(
                "Jira credentials not configured. Set JIRA_URL, JIRA_EMAIL, "
                "and JIRA_API_TOKEN in your environment."
            )
        self.base_url = settings.jira_url.rstrip("/")
        self.auth = (settings.jira_email, settings.jira_api_token)

    async def authenticate(self) -> bool:
        async with httpx.AsyncClient(auth=self.auth, timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/rest/api/3/myself")
            return response.status_code == 200

    async def fetch(self, config: dict) -> list[Ticket]:
        board_id = config.get("board_id")
        sprint_id = config.get("sprint_id")

        if sprint_id:
            jql = f"sprint = {sprint_id}"
        elif board_id:
            jql = f"project = {board_id}"
        else:
            raise ValueError("config must include either 'board_id' or 'sprint_id'")

        async with httpx.AsyncClient(auth=self.auth, timeout=15.0) as client:
            response = await client.get(
                f"{self.base_url}/rest/api/3/search",
                params={
                    "jql": jql,
                    "maxResults": 100,
                    "fields": "summary,description,status,assignee,priority,"
                              "labels,created,updated,sprint",
                },
            )
            response.raise_for_status()
            data = response.json()

        tickets: list[Ticket] = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            raw_status = fields["status"]["name"]

            tickets.append(Ticket(
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
            ))

        return tickets

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
