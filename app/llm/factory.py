from app.config import settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider()
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    if settings.llm_provider == "groq":
        return GroqProvider()
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not yet implemented.")
