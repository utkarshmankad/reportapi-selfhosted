"""Anthropic LLM provider."""
import httpx
from app.llm.base import LLMProvider
from app.config import settings


class AnthropicProvider(LLMProvider):
    MODEL = "claude-sonnet-4-5"
    API_VERSION = "2023-06-01"

    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.api_key = settings.anthropic_api_key

    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                },
                json={
                    "model": self.MODEL,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_content},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["content"][0]["text"]
        tokens_used = data["usage"]["input_tokens"] + data["usage"]["output_tokens"]

        return text, tokens_used
