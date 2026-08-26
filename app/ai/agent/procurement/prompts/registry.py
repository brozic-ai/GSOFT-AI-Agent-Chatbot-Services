import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / "v1"


def _extract_prompt_text(prompt_obj, role_target: str = "system") -> str:
    """Helper trích xuất nội dung từ Langfuse Chat/Text Prompt."""
    if not prompt_obj:
        return ""
    if isinstance(prompt_obj.prompt, list):
        for msg in prompt_obj.prompt:
            if msg.get("role") == role_target:
                return msg.get("content", "")
        if prompt_obj.prompt:
            return prompt_obj.prompt[0].get("content", "")
    elif isinstance(prompt_obj.prompt, str):
        return prompt_obj.prompt
    return str(prompt_obj.prompt)


def get_system_prompt() -> str:
    """
    Nạp System Prompt cho Procurement Agent từ Langfuse ('procurement').
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[PROCUREMENT-PROMPT] Lỗi lấy prompt 'procurement' từ Langfuse: %s", ex)

    return "Bạn là Trợ lý Mua sắm Doanh nghiệp BVBank (gAMSPro)."


def get_user_prompt(
    query: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Nạp và format User Prompt từ Langfuse prompt 'procurement'."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                    )
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
        logger.warning("[PROCUREMENT-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)

    return query


def get_procurement_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """Lấy toàn bộ messages (System + User) từ Chat Prompt 'procurement' trên Langfuse."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                    )
                except Exception:
                    compiled = prompt_obj.compile()

                messages: List[BaseMessage] = []
                if isinstance(compiled, list):
                    for m in compiled:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        if role == "system":
                            messages.append(SystemMessage(content=content))
                        elif role == "user":
                            messages.append(HumanMessage(content=content))
                        elif role in ("assistant", "ai"):
                            messages.append(AIMessage(content=content))

                    if len(messages) == 1 and isinstance(messages[0], SystemMessage):
                        messages.append(HumanMessage(content=query))

                    if messages:
                        return messages
    except Exception as ex:
        logger.warning("[PROCUREMENT-MESSAGES] Lỗi compile prompt procurement từ Langfuse: %s", ex)

    return [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=query),
    ]
