"""Abstract LLMProvider interface."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int, bool]:
        """
        Returns a tuple of (generated_text, tokens_used, truncated) — truncated
        is True when the provider cut the response off before completion
        (e.g. hit its own output token limit) rather than finishing normally.
        """
        ...
