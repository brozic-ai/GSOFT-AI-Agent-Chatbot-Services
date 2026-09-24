import logging
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)


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
    Nạp System Prompt cho Router Node:
    - Nạp trực tiếp 100% từ Langfuse ('procurement') với cache_ttl_seconds=60.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content and len(content.strip()) > 10:
                logger.info(
                    "[PROCUREMENT-PROMPT] ✅ Đã nạp thành công prompt 'procurement' (v%s) từ Langfuse",
                    getattr(prompt_obj, "version", "latest"),
                )
                return content
    except Exception as ex:
        logger.warning("[PROCUREMENT-PROMPT] ⚠️ Không thể nạp prompt 'procurement' từ Langfuse: %s", ex)

    return ""


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
    """
    Lấy toàn bộ messages (System + User) từ Chat Prompt 'procurement' trên Langfuse.
    Compile các biến: query, chat_history.
    """
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
        logger.warning("[PROCUREMENT-MESSAGES] Lỗi compile prompt 'procurement' từ Langfuse: %s", ex)

    sys_text = get_system_prompt()
    msgs: List[BaseMessage] = []
    if sys_text:
        msgs.append(SystemMessage(content=sys_text))
    msgs.append(HumanMessage(content=query))
    return msgs


def get_generator_prompt() -> str:
    """
    Nạp System Prompt cho Generator Node:
    - Nạp trực tiếp 100% từ Langfuse ('procurement_generator') với cache_ttl_seconds=60.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement_generator", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content and len(content.strip()) > 10:
                logger.info(
                    "[PROCUREMENT-GENERATOR] ✅ Đã nạp thành công prompt 'procurement_generator' (v%s) từ Langfuse",
                    getattr(prompt_obj, "version", "latest"),
                )
                return content
    except Exception as ex:
        logger.warning("[PROCUREMENT-GENERATOR] ⚠️ Không thể nạp prompt 'procurement_generator' từ Langfuse: %s", ex)

    return ""


def get_generator_messages(
    query: str,
    tool_result: str,
    chat_history: list[dict] | None = None,
) -> List[BaseMessage]:
    """
    Lấy toàn bộ messages (System + User Prompt) cho Generator Node:
    - Nạp trực tiếp từ Chat Prompt 'procurement_generator' trên Langfuse.
    - Compile các biến: chat_history, query, tool_result.
    """
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement_generator", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                        tool_result=tool_result,
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

                    if messages:
                        return messages
    except Exception as ex:
        logger.warning("[PROCUREMENT-GENERATOR] Lỗi compile prompt 'procurement_generator' từ Langfuse: %s", ex)

    sys_text = get_generator_prompt()
    user_payload = f"<chat_history>\n{history_text}\n</chat_history>\n\n<user_query>\n{query}\n</user_query>\n\n<tool_result>\n{tool_result}\n</tool_result>"
    msgs: List[BaseMessage] = []
    if sys_text:
        msgs.append(SystemMessage(content=sys_text))
    msgs.append(HumanMessage(content=user_payload))
    return msgs


# Alias để tương thích ngược
get_responder_prompt = get_generator_prompt
