import pytest
import respx
import httpx
from app.llm.groq_provider import GroqProvider


@pytest.mark.asyncio
@respx.mock
async def test_generate_returns_text_and_tokens(monkeypatch):
    monkeypatch.setattr("app.config.settings.groq_api_key", "fake-key")

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "Sprint velocity increased 12%."}}],
            "usage": {"total_tokens": 245},
        })
    )

    provider = GroqProvider()
    text, tokens = await provider.generate(
        system_prompt="You are a business analyst.",
        user_content="Summarise this sprint data.",
        max_tokens=500,
    )

    assert text == "Sprint velocity increased 12%."
    assert tokens == 245


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.groq_api_key", None)
    with pytest.raises(ValueError):
        GroqProvider()
