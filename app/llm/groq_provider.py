"""Groq LLM provider — OpenAI-compatible chat completions API."""
import httpx
from app.llm.base import LLMProvider
from app.config import settings


class GroqProvider(LLMProvider):
    MODEL = "llama-3.3-70b-versatile"

    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        self.api_key = settings.groq_api_key

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

        text = data["choices"][0]["message"]["content"]
        tokens_used = data["usage"]["total_tokens"]

        return text, tokens_used
