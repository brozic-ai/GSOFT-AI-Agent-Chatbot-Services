# llm/factory.py
import os
from .base import BaseLLMProvider
from .providers.gemini import GeminiProvider

def get_llm_provider() -> BaseLLMProvider:
    provider_name = os.getenv("AI_PROVIDER", "gemini")

    if provider_name == "gemini":
        return GeminiProvider(api_key=os.getenv("GEMINI_API_KEY"))
    elif provider_name == "azure_open_ai":
        # TODO: from llm.providers.azure_openai import AzureOpenAIProvider
        ...
    else:
        raise ValueError(f"Không hỗ trợ provider: {provider_name}")