from app.config import Settings, settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider


def get_llm_provider(config: Settings | None = None) -> LLMProvider:
    config = config or settings
    if config.llm_provider == "openai":
        return OpenAIProvider(config)
    if config.llm_provider == "anthropic":
        return AnthropicProvider(config)
    if config.llm_provider == "ollama":
        return OllamaProvider(config)
    if config.llm_provider == "groq":
        return GroqProvider(config)
    raise NotImplementedError(f"LLM provider '{config.llm_provider}' is not yet implemented.")
