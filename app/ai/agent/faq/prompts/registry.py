import logging
from typing import Any, Optional

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)


def _extract_prompt_text(prompt_obj: Any, role_target: str = "system") -> str:
    """Helper trích xuất nội dung text từ Langfuse Chat/Text Prompt."""
    if not prompt_obj:
        return ""
    if hasattr(prompt_obj, "prompt"):
        prompt_data = prompt_obj.prompt
    else:
        prompt_data = prompt_obj

    if isinstance(prompt_data, list):
        for msg in prompt_data:
            if isinstance(msg, dict) and msg.get("role") == role_target:
                return msg.get("content", "")
        if prompt_data and isinstance(prompt_data[0], dict):
            return prompt_data[0].get("content", "")
    elif isinstance(prompt_data, str):
        return prompt_data
    return str(prompt_data)


def get_system_prompt() -> str:
    """
    Nạp System Prompt cho FAQ Agent trực tiếp từ Langfuse ('faq').
    Tự động cache 60s và fallback an toàn nếu không kết nối được Langfuse.
    Hoàn toàn không nạp file prompt local.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("faq", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[FAQ-PROMPT] Lỗi lấy prompt 'faq' từ Langfuse: %s", ex)

    # Fallback dự phòng tối thiểu khi không kết nối được Langfuse
    return (
        "You are the internal AI assistant of BVBank, specialized in answering simple, "
        "fixed-answer FAQs about company policies, workplace rules, internal services, "
        "and general company information."
    )


class PromptLoader:
    """Class tương thích ngược (deprecated) - chuyển tiếp trực tiếp đến Langfuse prompt."""

    def __init__(self, task: str = "faq", version: str = "v1"):
        self.task = task
        self.version = version

    def load_system(self) -> str:
        return get_system_prompt()

    def load_user(self, **kwargs) -> str:
        return kwargs.get("query", "")
