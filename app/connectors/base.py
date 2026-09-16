"""Abstract Connector interface."""

from abc import ABC, abstractmethod

from app.models.ticket import Ticket


class Connector(ABC):
    @abstractmethod
    async def authenticate(self) -> bool:
        """Validate credentials. Return True if valid, False otherwise."""
        ...

    @abstractmethod
    async def fetch(self, config: dict) -> list[Ticket]:
        """Fetch tickets matching the given filter config."""
        ...
