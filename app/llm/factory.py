from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.config import settings


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    raise NotImplementedError(
        f"LLM provider '{settings.llm_provider}' is not yet implemented. "
        f"Available in v0.1: openai"
    )
