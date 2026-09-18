import httpx
import pytest
import respx

from app.llm.ollama_provider import OllamaProvider


@pytest.mark.asyncio
@respx.mock
async def test_generate_returns_text_and_tokens(monkeypatch):
    monkeypatch.setattr("app.config.settings.ollama_base_url", "http://ollama:11434")

    respx.post("http://ollama:11434/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"content": "Sprint velocity increased 12%."},
                "prompt_eval_count": 180,
                "eval_count": 40,
            },
        )
    )

    provider = OllamaProvider()
    text, tokens, truncated = await provider.generate(
        system_prompt="You are a business analyst.",
        user_content="Summarise this sprint data.",
        max_tokens=500,
    )

    assert text == "Sprint velocity increased 12%."
    assert tokens == 220
    assert truncated is False


@pytest.mark.asyncio
@respx.mock
async def test_generate_flags_truncated_response(monkeypatch):
    monkeypatch.setattr("app.config.settings.ollama_base_url", "http://ollama:11434")

    respx.post("http://ollama:11434/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"content": "Cut off mid-"},
                "prompt_eval_count": 180,
                "eval_count": 500,
                "done_reason": "length",
            },
        )
    )

    provider = OllamaProvider()
    _, _, truncated = await provider.generate(system_prompt="s", user_content="u", max_tokens=500)

    assert truncated is True
