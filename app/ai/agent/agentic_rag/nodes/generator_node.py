import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.agent.agentic_rag.prompts.registry import get_generator_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def generator_node(state: AgenticRagState) -> dict[str, Any]:
    """Node 4: Generator Node — Tổng hợp câu trả lời cuối cùng bám sát tài liệu với cam kết Zero-Hallucination."""
    documents = (
        state.get("documents", [])
        if isinstance(state, dict)
        else getattr(state, "documents", [])
    )
    citations = (
        state.get("citations", [])
        if isinstance(state, dict)
        else getattr(state, "citations", [])
    )
    is_relevant = (
        state.get("is_relevant", False)
        if isinstance(state, dict)
        else getattr(state, "is_relevant", False)
    )
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    messages = (
        state.get("messages", [])
        if isinstance(state, dict)
        else getattr(state, "messages", [])
    )

    # 1. Trường hợp không gọi Tool (trả lời trực tiếp/chitchat từ agent_node)
    if not documents and not citations:
        # Nếu message cuối cùng của agent_node đã là AIMessage không có tool_calls
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage) and not getattr(
                last_msg, "tool_calls", None
            ):
                content = str(last_msg.content)
                return {"final_answer": content}

    # 2. Trường hợp tra cứu nhưng không tìm thấy tài liệu phù hợp (Zero-Hallucination)
    if not documents or not is_relevant:
        answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."
        return {"final_answer": answer, "messages": [AIMessage(content=answer)]}

    # 3. Trường hợp có tài liệu liên quan -> Build ngữ cảnh trích dẫn và sinh câu trả lời
    context_parts: list[str] = []
    for i, doc in enumerate(documents, 1):
        cit = citations[i - 1] if i - 1 < len(citations) else {}
        source = (
            cit.get("source")
            or cit.get("file_name")
            or cit.get("document_name")
            or "Tài liệu"
            if isinstance(cit, dict)
            else "Tài liệu"
        )
        page = (
            cit.get("page")
            or cit.get("page_number")
            or cit.get("slide")
            or ""
            if isinstance(cit, dict)
            else ""
        )
        page_info = f", Trang {page}" if page else ""
        section = (
            cit.get("section")
            or cit.get("slide_title")
            or cit.get("page_title")
            or ""
            if isinstance(cit, dict)
            else ""
        )
        section_info = f" - Mục: {section}" if section else ""

        citation_label = f"[Nguồn {i}: {source}{page_info}{section_info}]"
        context_parts.append(f"{citation_label}\n{doc}")

    context_str = "\n\n---\n\n".join(context_parts)

    llm = get_chat_model()
    generator_prompt = get_generator_prompt()

    response = await llm.ainvoke(
        [
            SystemMessage(content=generator_prompt),
            HumanMessage(
                content=f"Câu hỏi của người dùng: {user_query}\n\nNGỮ CẢNH TÀI LIỆU:\n{context_str}"
            ),
        ]
    )

    answer = (
        response.content
        if hasattr(response, "content")
        else str(response)
    )
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}
