import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.agent.agentic_rag.prompts.registry import get_generator_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def generator_node(state: AgenticRagState) -> dict[str, Any]:
    """Generator Node: Tổng hợp câu trả lời cuối cùng bám sát tài liệu với chuẩn Zero-Hallucination và Inline Footnotes."""
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

    if not user_query and messages:
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and getattr(m, "type", "") in ("human", "user"):
                user_query = str(m.content)
                break

    # 1. Trường hợp không có tài liệu (Zero-Hallucination)
    if not documents:
        answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."
        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
            "citations": [],
        }

    # 2. Sử dụng RagContextBuilder để chuẩn hóa, khử trùng lặp và đóng gói [ĐOẠN n]
    from app.ai.rag.context.builder import RagContextBuilder, determine_max_tokens

    context_str, used_metas, used_citations = RagContextBuilder.build(
        documents=documents,
        metadatas=citations,
    )

    if not context_str.strip():
        answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."
        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
            "citations": [],
        }

    # 3. Tính toán max_tokens động theo số bước nghiệp vụ trong context
    dynamic_max_tokens = determine_max_tokens(context_str)
    llm = get_chat_model(max_tokens=dynamic_max_tokens)
    generator_prompt = get_generator_prompt()

    response = await llm.ainvoke(
        [
            SystemMessage(content=generator_prompt),
            HumanMessage(
                content=f"Câu hỏi của cán bộ nhân viên: {user_query}\n\nNGỮ CẢNH TÀI LIỆU QUY CHẾ / HDSD:\n{context_str}"
            ),
        ]
    )

    answer = (
        response.content
        if hasattr(response, "content")
        else str(response)
    )

    # Đảm bảo trả về string sạch
    if isinstance(answer, list):
        answer = "".join(str(part) for part in answer)
    else:
        answer = str(answer)

    return {
        "final_answer": answer,
        "messages": [AIMessage(content=answer)],
        "citations": used_citations if used_citations else citations,
    }
