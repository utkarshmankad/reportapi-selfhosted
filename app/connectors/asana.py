"""Asana connector.

Asana has no native board/sprint split — work lives in projects, optionally
grouped into sections. The connector reuses the Jira-shaped `board_id` /
`sprint_id` filter contract: `board_id` maps to a project GID, `sprint_id`
(when given) maps to a section GID within that project.
"""

import httpx

from app.config import Settings, settings
from app.connectors.base import Connector, FetchResult
from app.models.report import validate_connector_scope
from app.models.ticket import Ticket

API_BASE = "https://app.asana.com/api/1.0"

PAGE_SIZE = 100
MAX_PAGES = 50
MAX_RECORDS = 5000

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
    def __init__(self, config: Settings | None = None):
        config = config or settings
        if not config.asana_pat:
            raise ValueError("Asana credentials not configured. Set ASANA_PAT in your environment.")
        self.headers = {"Authorization": f"Bearer {config.asana_pat}"}

    async def authenticate(self) -> bool:
        async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
            response = await client.get(f"{API_BASE}/users/me")
            return response.status_code == 200

    async def fetch(self, config: dict) -> FetchResult:
        project_gid = config.get("board_id")
        section_gid = config.get("sprint_id")
        validate_connector_scope("asana", project_gid, section_gid)

        opt_fields = (
            "name,notes,completed,assignee.name,tags.name,"
            "created_at,modified_at,memberships.section.name,memberships.section.gid,"
            "memberships.project.gid,permalink_url,"
            "custom_fields.name,custom_fields.display_value"
        )
        if section_gid:
            url = f"{API_BASE}/sections/{section_gid}/tasks"
        else:
            url = f"{API_BASE}/projects/{project_gid}/tasks"

        tickets: list[Ticket] = []
        truncated = False
        truncation_reason: str | None = None
        offset: str | None = None
        seen_offsets: set[str] = set()

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            for page in range(MAX_PAGES):
                params = {"opt_fields": opt_fields, "limit": PAGE_SIZE}
                if offset:
                    params["offset"] = offset

                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    if page == 0:
                        raise
                    truncated = True
                    truncation_reason = "Asana page fetch failed"
                    break

                for task in data.get("data", []):
                    section_name = self._extract_section_name(task, project_gid, section_gid)
                    tickets.append(
                        Ticket(
                            id=task["gid"],
                            title=task.get("name", ""),
                            description=task.get("notes", "") or "",
                            status=self._resolve_status(task, section_name),
                            assignee=(task.get("assignee") or {}).get("name"),
                            priority=self._extract_priority(task),
                            labels=[
                                tag.get("name") for tag in task.get("tags", []) if tag.get("name")
                            ],
                            created_at=task["created_at"],
                            updated_at=task["modified_at"],
                            sprint=section_name,
                            url=task.get("permalink_url", ""),
                        )
                    )

                if len(tickets) >= MAX_RECORDS:
                    next_offset = (data.get("next_page") or {}).get("offset")
                    truncated = bool(next_offset)
                    if truncated:
                        truncation_reason = f"Reached the {MAX_RECORDS}-record fetch limit"
                    break

                next_offset = (data.get("next_page") or {}).get("offset")
                if not next_offset:
                    break
                if next_offset in seen_offsets:
                    truncated = True
                    truncation_reason = "Asana returned a repeated pagination cursor"
                    break
                seen_offsets.add(next_offset)
                offset = next_offset
            else:
                truncated = True
                truncation_reason = f"Reached the {MAX_PAGES}-page fetch limit"

        return FetchResult(
            tickets=tickets, truncated=truncated, truncation_reason=truncation_reason
        )

    @staticmethod
    def _resolve_status(task: dict, section_name: str | None) -> str:
        # Asana's `completed` flag is the authoritative source-of-truth state:
        # a task marked done stays done regardless of which section (e.g. a
        # stale "In Progress" section) it's still sitting in.
        if task.get("completed"):
            return "done"
        if section_name:
            hint = SECTION_STATUS_HINTS.get(section_name.strip().lower())
            if hint:
                return hint
        return "todo"

    @staticmethod
    def _extract_section_name(
        task: dict, project_gid: str | None, section_gid: str | None
    ) -> str | None:
        # A task can belong to several projects at once, each with its own
        # section membership. When the response identifies which project a
        # membership belongs to, only the one matching the queried
        # project/section is relevant — but a project-scoped task list
        # commonly returns a single membership without that project gid, in
        # which case it's unambiguous and used as-is.
        memberships = [
            m for m in (task.get("memberships") or []) if (m.get("section") or {}).get("name")
        ]
        if not memberships:
            return None
        if len(memberships) == 1:
            return memberships[0]["section"]["name"]
        for membership in memberships:
            section = membership["section"]
            if section_gid and section.get("gid") == section_gid:
                return section["name"]
            if project_gid and (membership.get("project") or {}).get("gid") == project_gid:
                return section["name"]
        return None

    @staticmethod
    def _extract_priority(task: dict) -> str | None:
        # Asana has no built-in priority field — many teams model it as a
        # custom field named "Priority". Best-effort lookup, else None.
        for field in task.get("custom_fields", []):
            if (field.get("name") or "").strip().lower() == "priority":
                return field.get("display_value")
        return None
