import logging
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)


def _extract_prompt_text(prompt_obj: Any, role_target: str = "system") -> str:
    """Helper trích xuất nội dung từ Langfuse Chat/Text Prompt."""
    if not prompt_obj:
        return ""
    if hasattr(prompt_obj, "prompt"):
        prompt_data = prompt_obj.prompt
    else:
        prompt_data = prompt_obj

    if isinstance(prompt_data, list):
        for msg in prompt_data:
            if msg.get("role") == role_target:
                return msg.get("content", "")
        if prompt_data:
            return prompt_data[0].get("content", "")
    elif isinstance(prompt_data, str):
        return prompt_data
    return str(prompt_data)


def get_supervisor_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """
    Lấy danh sách messages (System, User) trực tiếp từ Chat Prompt 'supervisor' trên Langfuse.
    Toàn bộ prompt (bao gồm hướng dẫn, examples và cấu trúc schema) được quản lý trực tiếp trên Langfuse.
    """
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )

    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=10)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                    )
                except Exception:
                    compiled = prompt_obj.compile()

                langchain_messages: List[BaseMessage] = []
                if isinstance(compiled, list):
                    for m in compiled:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        if role == "system":
                            langchain_messages.append(SystemMessage(content=content))
                        elif role == "user":
                            langchain_messages.append(HumanMessage(content=content))
                        elif role in ("assistant", "ai"):
                            langchain_messages.append(AIMessage(content=content))

                    # Nếu prompt trên Langfuse chỉ chứa System message, tự động kèm Human message
                    if len(langchain_messages) == 1 and isinstance(langchain_messages[0], SystemMessage):
                        langchain_messages.append(HumanMessage(content=query))

                    if langchain_messages:
                        return langchain_messages

                elif isinstance(compiled, str):
                    return [
                        SystemMessage(content=compiled),
                        HumanMessage(content=query),
                    ]
    except Exception as ex:
        logger.warning("[SUPERVISOR-PROMPT] Lỗi lấy prompt 'supervisor' từ Langfuse: %s", ex)

    # Fallback tối giản nếu Langfuse tạm thời không khả dụng
    return [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=query),
    ]


def get_system_prompt() -> str:
    """Lấy riêng System Prompt từ Chat/Text Prompt 'supervisor' trên Langfuse."""
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=10)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[SUPERVISOR-SYSTEM-PROMPT] Lỗi lấy prompt từ Langfuse: %s", ex)

    return "You are an expert Intent Classifier for the BVBank AI Assistant system."


def get_user_prompt(query: str, chat_history: list[dict] | None = None) -> str:
    """Lấy User Prompt compiled từ Chat Prompt 'supervisor' trên Langfuse."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=10)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(query=query, chat_history=history_text)
                    if isinstance(compiled, list):
                        for m in compiled:
                            if m.get("role") == "user":
                                return m.get("content", query)
                except Exception:
                    pass
                user_content = _extract_prompt_text(prompt_obj, role_target="user")
                if user_content:
                    return user_content
    except Exception as ex:
        logger.warning("[SUPERVISOR-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)

    return query
