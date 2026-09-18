import httpx
import pytest
import respx

from app.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
@respx.mock
async def test_generate_returns_text_and_tokens(monkeypatch):
    monkeypatch.setattr("app.config.settings.openai_api_key", "fake-key")

    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Sprint velocity increased 12%."}}],
                "usage": {"total_tokens": 245},
            },
        )
    )

    provider = OpenAIProvider()
    text, tokens, truncated = await provider.generate(
        system_prompt="You are a business analyst.",
        user_content="Summarise this sprint data.",
        max_tokens=500,
    )

    assert text == "Sprint velocity increased 12%."
    assert tokens == 245
    assert truncated is False


@pytest.mark.asyncio
@respx.mock
async def test_generate_flags_truncated_response(monkeypatch):
    monkeypatch.setattr("app.config.settings.openai_api_key", "fake-key")

    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Cut off mid-"}, "finish_reason": "length"}],
                "usage": {"total_tokens": 500},
            },
        )
    )

    provider = OpenAIProvider()
    _, _, truncated = await provider.generate(system_prompt="s", user_content="u", max_tokens=500)

    assert truncated is True


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.openai_api_key", None)
    with pytest.raises(ValueError):
        OpenAIProvider()
