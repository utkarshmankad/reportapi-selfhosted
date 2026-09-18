import httpx
import pytest
import respx

from app.llm.anthropic_provider import AnthropicProvider


@pytest.mark.asyncio
@respx.mock
async def test_generate_returns_text_and_tokens(monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", "fake-key")

    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Sprint velocity increased 12%."}],
                "usage": {"input_tokens": 200, "output_tokens": 45},
            },
        )
    )

    provider = AnthropicProvider()
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
    monkeypatch.setattr("app.config.settings.anthropic_api_key", "fake-key")

    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Cut off mid-"}],
                "usage": {"input_tokens": 200, "output_tokens": 500},
                "stop_reason": "max_tokens",
            },
        )
    )

    provider = AnthropicProvider()
    _, _, truncated = await provider.generate(system_prompt="s", user_content="u", max_tokens=500)

    assert truncated is True


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", None)
    with pytest.raises(ValueError):
        AnthropicProvider()
