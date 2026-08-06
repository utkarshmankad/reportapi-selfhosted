from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.ollama_provider import OllamaProvider
from app.config import settings


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider()
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    raise NotImplementedError(
        f"LLM provider '{settings.llm_provider}' is not yet implemented."
    )
