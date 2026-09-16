"""Ollama LLM provider — runs fully local, no internet traffic."""

import httpx

from app.config import settings
from app.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    MODEL = "llama3.2"

    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")

    async def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.MODEL,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["message"]["content"]
        tokens_used = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)

        return text, tokens_used
