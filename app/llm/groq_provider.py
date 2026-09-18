"""Groq LLM provider — OpenAI-compatible chat completions API."""

import httpx

from app.config import Settings, settings
from app.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    MODEL = "llama-3.3-70b-versatile"

    def __init__(self, config: Settings | None = None):
        config = config or settings
        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        self.api_key = config.groq_api_key

    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
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

        choice = data["choices"][0]
        text = choice["message"]["content"]
        tokens_used = data["usage"]["total_tokens"]
        truncated = choice.get("finish_reason") == "length"

        return text, tokens_used, truncated
