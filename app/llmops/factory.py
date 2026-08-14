from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings


def _build_gemini(**overrides) -> BaseChatModel:
    """ """
    return ChatGoogleGenerativeAI(
        model=overrides.pop("model", settings.GEMINI_MODEL),
        google_api_key=settings.GEMINI_API_KEY,
        temperature=overrides.pop("temperature", settings.LLM_TEMPERATURE),
        max_output_tokens=overrides.pop("max_tokens", settings.LLM_MAX_TOKENS),
        **overrides,
    )


def _build_openai_compat(**overrides) -> BaseChatModel:
    """ """
    return ChatOpenAI(
        model=overrides.pop("model", settings.LLM_MODEL),
        base_url=overrides.pop("base_url", settings.LLM_BASE_URL),
        api_key=overrides.pop("api_key", settings.LLM_API_KEY),
        temperature=overrides.pop("temperature", settings.LLM_TEMPERATURE),
        max_tokens=overrides.pop("max_tokens", settings.LLM_MAX_TOKENS),
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        **overrides,
    )


_BUILDER = {
    "gemini": _build_gemini,
    "openai_compat": _build_openai_compat,
    "vllm": _build_openai_compat,  # vLLM dung OpenAI-compatible API
    "ollama": _build_openai_compat,  # Ollama OpenAI-compatible API: http://localhost:11434/v1
}


@lru_cache(maxsize=8)
def get_chat_model(provider: str | None = None, **overrides) -> BaseChatModel:
    name = provider or settings.AI_PROVIDER
    if name not in _BUILDER:
        raise ValueError(f"UnKnown provider: {name}. Options: {list(_BUILDER)}")
    return _BUILDER[name](**overrides)
