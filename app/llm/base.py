"""Abstract LLMProvider interface."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        """
        Returns a tuple of (generated_text, tokens_used).
        """
        ...
