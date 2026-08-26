import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / "v1"


def get_supervisor_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """
    Lấy danh sách messages (System, User) trực tiếp từ Chat Prompt 'supervisor' trên Langfuse.
    Few-shot examples đã được tích hợp trực tiếp vào user_prompt trên Langfuse.
    """
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )

    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=60)
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
        logger.warning("[SUPERVISOR-PROMPT] Lỗi lấy prompt từ Langfuse: %s", ex)

    return [
        SystemMessage(content="You are an expert Intent Classifier for the BVBank AI Assistant system."),
        HumanMessage(content=query),
    ]


def get_system_prompt() -> str:
    """Lấy riêng System Prompt từ Langfuse prompt 'supervisor'."""
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=60)
            if prompt_obj:
                if isinstance(prompt_obj.prompt, list):
                    for msg in prompt_obj.prompt:
                        if msg.get("role") == "system":
                            return msg.get("content", "")
                    if prompt_obj.prompt:
                        return prompt_obj.prompt[0].get("content", "")
                elif isinstance(prompt_obj.prompt, str):
                    return prompt_obj.prompt
    except Exception as ex:
        logger.warning("[SUPERVISOR-SYSTEM-PROMPT] Lỗi lấy prompt từ Langfuse: %s", ex)
    return "You are an expert Intent Classifier for the BVBank AI Assistant system."


def get_user_prompt(query: str, chat_history: list[dict] | None = None) -> str:
    """Lấy User Prompt compiled từ Langfuse prompt 'supervisor'."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("supervisor", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(query=query, chat_history=history_text)
                    if isinstance(compiled, list):
                        for m in compiled:
                            if m.get("role") == "user":
                                return m.get("content", query)
                except Exception:
                    pass
    except Exception as ex:
        logger.warning("[SUPERVISOR-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)
    return query
