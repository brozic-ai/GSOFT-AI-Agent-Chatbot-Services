from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.model_levels import normalize_model_level


def _build_gemini(**overrides) -> BaseChatModel:
    """Khởi tạo ChatGoogleGenerativeAI client cho Gemini."""
    return ChatGoogleGenerativeAI(
        model=overrides.pop("model", settings.GEMINI_MODEL),
        google_api_key=settings.GEMINI_API_KEY,
        temperature=overrides.pop("temperature", settings.LLM_TEMPERATURE),
        max_output_tokens=overrides.pop("max_tokens", settings.LLM_MAX_TOKENS),
        **overrides,
    )


def _build_openai_compat(**overrides) -> BaseChatModel:
    """Khởi tạo ChatOpenAI client tương thích chuẩn OpenAI API (vLLM / Ollama / llama.cpp)."""
    return ChatOpenAI(
        model=overrides.pop("model", settings.LLM_MODEL),
        base_url=overrides.pop("base_url", settings.LLM_BASE_URL),
        api_key=overrides.pop("api_key", settings.LLM_API_KEY),
        temperature=overrides.pop("temperature", settings.LLM_TEMPERATURE),
        max_tokens=overrides.pop("max_tokens", settings.LLM_MAX_TOKENS),
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        **overrides,
    )


import logging

logger = logging.getLogger(__name__)

_BUILDER = {
    "gemini": _build_gemini,
    "openai_compat": _build_openai_compat,
    "vllm": _build_openai_compat,  # vLLM dung OpenAI-compatible API
    "ollama": _build_openai_compat,  # Ollama OpenAI-compatible API: http://localhost:11434/v1
}


@lru_cache(maxsize=16)
def get_chat_model(provider: str | None = None, **overrides) -> BaseChatModel:
    """Khởi tạo Chat Model theo provider xác định hoặc mặc định từ settings."""
    name = provider or settings.AI_PROVIDER
    if name not in _BUILDER:
        raise ValueError(f"UnKnown provider: {name}. Options: {list(_BUILDER)}")
    return _BUILDER[name](**overrides)


def get_router_model(**overrides) -> BaseChatModel:
    """
    Khởi tạo mô hình chuyên trách cho Llama Router / Supervisor Intent Classifier.
    Sử dụng model siêu nhẹ (vd Qwen3.5-2B / Llama-3.2) để đạt chi phí phân loại thấp; latency phụ thuộc máy chủ và prompt.
    """
    provider = getattr(settings, "ROUTER_PROVIDER", "vllm")
    model_name = getattr(settings, "ROUTER_MODEL", "Qwen3.5-2B_Q4_k_m")

    logger.info(
        "[FACTORY] Khởi tạo Router Model (provider=%s, model=%s)", provider, model_name
    )
    primary_model = get_chat_model(provider=provider, model=model_name, **overrides)

    fallback_provider = getattr(settings, "FALLBACK_AI_PROVIDER", None)
    if fallback_provider and fallback_provider != provider:
        try:
            fallback_model = get_chat_model(provider=fallback_provider, **overrides)
            return primary_model.with_fallbacks([fallback_model])
        except Exception as ex:  # noqa: BLE001
            logger.warning("[FACTORY] Không thể gắn fallback cho Router Model: %s", ex)

    return primary_model


def get_model_for_level(
    level: str | None = "medium",
    enable_fallback: bool = True,
    **overrides,
) -> BaseChatModel:
    """
    Định tuyến Model linh hoạt (Dynamic Model Routing) theo 3 cấp độ On-Premise:
    - 'low':    Model nhẹ, tốc độ cao (Qwen3.5-2B Local)
    - 'medium': Model cân bằng tiêu chuẩn (Qwen3.5-4B Local - Mặc định)
    - 'high':   Model chuyên sâu (Qwen3.5-4B Local với Context mở rộng)

    Hỗ trợ cơ chế tự động chuyển vùng (with_fallbacks) khi provider chính gặp sự cố.
    """
    normalized_level = normalize_model_level(level)

    level_map = {
        "low": (
            getattr(settings, "MODEL_LEVEL_LOW_PROVIDER", "vllm"),
            getattr(settings, "MODEL_LEVEL_LOW_MODEL", "Qwen3.5-2B_Q4_k_m"),
        ),
        "medium": (
            getattr(settings, "MODEL_LEVEL_MEDIUM_PROVIDER", "vllm"),
            getattr(settings, "MODEL_LEVEL_MEDIUM_MODEL", "Qwen3.5-4B-M-TS-Q4_K_M"),
        ),
        "high": (
            getattr(settings, "MODEL_LEVEL_HIGH_PROVIDER", "vllm"),
            getattr(settings, "MODEL_LEVEL_HIGH_MODEL", "Qwen3.5-4B-M-TS-Q4_K_M"),
        ),
    }

    provider, model_name = level_map[normalized_level]
    logger.info(
        "[FACTORY -> ROUTING] Định tuyến cấp độ '%s' -> Provider: %s, Model: %s",
        normalized_level,
        provider,
        model_name,
    )

    primary_model = get_chat_model(provider=provider, model=model_name, **overrides)

    if enable_fallback:
        fallback_provider = getattr(settings, "FALLBACK_AI_PROVIDER", None)
        if fallback_provider and fallback_provider != provider:
            try:
                fallback_model = get_chat_model(provider=fallback_provider, **overrides)
                return primary_model.with_fallbacks([fallback_model])
            except Exception as ex:  # noqa: BLE001
                logger.warning(
                    "[FACTORY] Không thể gắn fallback provider '%s': %s",
                    fallback_provider,
                    ex,
                )

    return primary_model


def get_context_params_for_level(level: str | None = "medium") -> dict[str, int]:
    """
    Lấy bộ tham số ngữ cảnh động (Dynamic Context Parameters) theo cấp độ model:
    - 'low':    top_k nhỏ (3), context ngắn (~6.000 ký tự) - Tốc độ tức thì
    - 'medium': top_k chuẩn (5), context chuẩn (~16.000 ký tự) - Cân bằng nghiệp vụ
    - 'high':   top_k mở rộng (10), context lớn (~24.000 ký tự) - Phân tích đa văn bản
    """
    normalized_level = normalize_model_level(level)

    if normalized_level == "low":
        return {
            "top_k": getattr(settings, "MODEL_LEVEL_LOW_TOP_K", 3),
            "max_chars": getattr(settings, "MODEL_LEVEL_LOW_MAX_CHARS", 6000),
        }
    if normalized_level == "high":
        return {
            "top_k": getattr(settings, "MODEL_LEVEL_HIGH_TOP_K", 10),
            "max_chars": getattr(settings, "MODEL_LEVEL_HIGH_MAX_CHARS", 24000),
        }
    return {
        "top_k": getattr(settings, "MODEL_LEVEL_MEDIUM_TOP_K", 5),
        "max_chars": getattr(settings, "MODEL_LEVEL_MEDIUM_MAX_CHARS", 16000),
    }
