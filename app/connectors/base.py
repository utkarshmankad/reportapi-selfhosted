"""Abstract Connector interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.ticket import Ticket


@dataclass
class FetchResult:
    """Result of a connector fetch, honest about whether it saw everything.

    `truncated` is True whenever the connector stopped before exhausting the
    source (page/record bound hit, a repeated cursor, or a later page
    failing) so callers never present a partial fetch as a complete report.
    """

    tickets: list[Ticket] = field(default_factory=list)
    truncated: bool = False
    truncation_reason: str | None = None


class Connector(ABC):
    @abstractmethod
    async def authenticate(self) -> bool:
        """Validate credentials. Return True if valid, False otherwise."""
        ...

    @abstractmethod
    async def fetch(self, config: dict) -> FetchResult:
        """Fetch tickets matching the given filter config."""
        ...
