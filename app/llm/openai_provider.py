"""OpenAI LLM provider."""

import httpx

from app.config import Settings, settings
from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    MODEL = "gpt-4o-mini"

    def __init__(self, config: Settings | None = None):
        config = config or settings
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.api_key = config.openai_api_key

    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.MODEL,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"]
        tokens_used = data["usage"]["total_tokens"]

        return text, tokens_used
