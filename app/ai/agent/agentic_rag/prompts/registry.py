import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client



logger = logging.getLogger(__name__)


def _extract_prompt_text(prompt_obj, role_target: str = "system") -> str:
    """Helper trích xuất nội dung text từ Langfuse Chat/Text Prompt."""
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
    Nạp System Prompt cho RAG Knowledge Agent từ Langfuse ('rag_system').
    Tự động cache 60s và fallback an toàn.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[RAG-SYSTEM-PROMPT] Lỗi lấy prompt 'rag_system' từ Langfuse: %s", ex)

    return "Bạn là Trợ lý Tra cứu Quy chế, Chính sách & Sổ tay Nghiệp vụ BVBank."



def get_generator_prompt() -> str:
    """
    Nạp Prompt cho Generator Node từ Langfuse ('rag_generator').
    Tự động cache 60s và có fallback prompt an toàn khi Langfuse không khả dụng hoặc lỗi kết nối.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_generator", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[RAG-GENERATOR-PROMPT] Lỗi kết nối/lấy prompt 'rag_generator' từ Langfuse: %s. Sử dụng prompt dự phòng.", ex)

    return (
        "Bạn là Trợ lý AI chuyên nghiệp hỗ trợ tra cứu và giải đáp quy chế, quy trình, chính sách "
        "và sổ tay nghiệp vụ của Ngân hàng TMCP Bản Việt (BVBank).\n"
        "Hãy trả lời câu hỏi của cán bộ nhân viên một cách chính xác, khách quan, đầy đủ và chuyên nghiệp "
        "dựa trên các thông tin trong NGỮ CẢNH TÀI LIỆU được cung cấp."
    )


def get_user_prompt(
    query: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Nạp và format User Prompt từ Langfuse prompt 'rag_system'."""
    history_text = (
        "\n".join(
            f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:]
        )
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
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
        logger.warning("[RAG-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)

    return query


def get_rag_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """Lấy toàn bộ messages (System + User) từ Chat Prompt 'rag_system' trên Langfuse."""
    history_text = (
        "\n".join(
            f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:]
        )
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
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
        logger.warning("[RAG-MESSAGES] Lỗi compile prompt rag_system từ Langfuse: %s", ex)

    return [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=query),
    ]
