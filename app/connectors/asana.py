"""Asana connector.

Asana has no native board/sprint split — work lives in projects, optionally
grouped into sections. The connector reuses the Jira-shaped `board_id` /
`sprint_id` filter contract: `board_id` maps to a project GID, `sprint_id`
(when given) maps to a section GID within that project.
"""

import httpx

from app.config import settings
from app.connectors.base import Connector
from app.models.ticket import Ticket

API_BASE = "https://app.asana.com/api/1.0"

# Asana tasks only carry a boolean `completed` flag natively. Status is
# inferred from the section a task sits in, falling back to completed/todo.
SECTION_STATUS_HINTS = {
    "to do": "todo",
    "todo": "todo",
    "backlog": "todo",
    "in progress": "in_progress",
    "doing": "in_progress",
    "blocked": "blocked",
    "review": "in_progress",
    "done": "done",
    "complete": "done",
    "completed": "done",
}


class AsanaConnector(Connector):
    def __init__(self):
        if not settings.asana_pat:
            raise ValueError("Asana credentials not configured. Set ASANA_PAT in your environment.")
        self.headers = {"Authorization": f"Bearer {settings.asana_pat}"}

    async def authenticate(self) -> bool:
        async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
            response = await client.get(f"{API_BASE}/users/me")
            return response.status_code == 200

    async def fetch(self, config: dict) -> list[Ticket]:
        project_gid = config.get("board_id")
        section_gid = config.get("sprint_id")

        if not project_gid and not section_gid:
            raise ValueError("config must include either 'board_id' or 'sprint_id'")

        opt_fields = (
            "name,notes,completed,assignee.name,tags.name,"
            "created_at,modified_at,memberships.section.name,permalink_url,"
            "custom_fields.name,custom_fields.display_value"
        )

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            if section_gid:
                url = f"{API_BASE}/sections/{section_gid}/tasks"
            else:
                url = f"{API_BASE}/projects/{project_gid}/tasks"

            response = await client.get(url, params={"opt_fields": opt_fields, "limit": 100})
            response.raise_for_status()
            data = response.json()

        tickets: list[Ticket] = []
        for task in data.get("data", []):
            tickets.append(
                Ticket(
                    id=task["gid"],
                    title=task.get("name", ""),
                    description=task.get("notes", "") or "",
                    status=self._resolve_status(task),
                    assignee=(task.get("assignee") or {}).get("name"),
                    priority=self._extract_priority(task),
                    labels=[tag.get("name") for tag in task.get("tags", []) if tag.get("name")],
                    created_at=task["created_at"],
                    updated_at=task["modified_at"],
                    sprint=self._extract_section_name(task),
                    url=task.get("permalink_url", ""),
                )
            )

        return tickets

    @staticmethod
    def _resolve_status(task: dict) -> str:
        section_name = AsanaConnector._extract_section_name(task)
        if section_name:
            hint = SECTION_STATUS_HINTS.get(section_name.strip().lower())
            if hint:
                return hint
        return "done" if task.get("completed") else "todo"

    @staticmethod
    def _extract_section_name(task: dict) -> str | None:
        memberships = task.get("memberships") or []
        if memberships and memberships[0].get("section"):
            return memberships[0]["section"].get("name")
        return None

    @staticmethod
    def _extract_priority(task: dict) -> str | None:
        # Asana has no built-in priority field — many teams model it as a
        # custom field named "Priority". Best-effort lookup, else None.
        for field in task.get("custom_fields", []):
            if (field.get("name") or "").strip().lower() == "priority":
                return field.get("display_value")
        return None
