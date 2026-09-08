"""
FAQ Agent Nodes — Các node xử lý trực tiếp trong quy trình tra cứu và trả lời FAQ.
Kiến trúc tối ưu Pipeline: Retrieve (Hybrid + Rerank) -> Generate (1 LLM call) / Fallback (Zero LLM call).
Loại bỏ vòng lặp ReAct dư thừa giúp giảm 2x latency và ngăn ngừa hallucination.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.agent.faq.prompts.registry import get_system_prompt
from app.ai.agent.faq.services.faq_retriever import retrieve_and_rerank_faqs
from app.ai.agent.faq.state import FAQState
from app.core.config import settings
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


def _extract_query_from_state(state: FAQState) -> str:
    """Trích xuất câu truy vấn của người dùng từ State."""
    if state.get("user_query"):
        return str(state["user_query"]).strip()

    messages = (
        list(state.get("messages", []))
        if isinstance(state, dict)
        else list(getattr(state, "messages", []))
    )
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", "") == "human":
            return str(msg.content).strip()
    return ""


async def retrieve_faq_node(state: FAQState) -> dict[str, Any]:
    """
    Node 1: Truy xuất và Rerank trực tiếp từ DB FAQ.
    Không gọi qua LLM Tool Calling -> giảm 1 vòng quay mạng và tiết kiệm chi phí.
    """
    query = _extract_query_from_state(state)
    if not query:
        logger.warning("[FAQ NODE] Không tìm thấy user_query trong state.")
        return {"retrieved_faqs": [], "citations": []}

    top_k = getattr(settings, "FAQ_RERANKER_TOP_K", 3)
    logger.info("[FAQ NODE] Đang truy xuất & rerank FAQ cho câu hỏi: '%s'", query[:80])

    retrieval_res = await retrieve_and_rerank_faqs(query=query, top_k=top_k)
    faqs = retrieval_res.get("faqs", [])
    citations = retrieval_res.get("citations", [])

    return {
        "retrieved_faqs": faqs,
        "citations": citations,
        "user_query": query,
    }


async def generate_faq_node(state: FAQState) -> dict[str, Any]:
    """
    Node 2: Tổng hợp câu trả lời thân thiện qua LLM (Single-turn LLM).
    LLM chỉ tập trung viết câu trả lời dựa trên thông tin FAQ đã được truy xuất chuẩn xác.
    """
    faqs = state.get("retrieved_faqs", [])
    query = _extract_query_from_state(state)

    # 1. Định dạng ngữ cảnh FAQ cho LLM
    context_chunks = []
    for idx, f in enumerate(faqs, start=1):
        context_chunks.append(
            f"--- [FAQ #{idx}] ---\n"
            f"Câu hỏi: {f['question']}\n"
            f"Câu trả lời: {f['answer']}\n"
        )
    faq_context = "\n".join(context_chunks)

    # 2. Tải System Prompt trực tiếp từ Langfuse
    system_prompt = get_system_prompt()

    # 3. Tạo prompt messages
    user_prompt = (
        f"Dưới đây là thông tin câu hỏi thường gặp (FAQ) được tìm thấy từ cơ sở dữ liệu nội bộ BVBank:\n\n"
        f"{faq_context}\n\n"
        f"Câu hỏi của nhân viên: {query}\n\n"
        f"Hãy trả lời câu hỏi của nhân viên dựa trên các thông tin FAQ ở trên một cách rõ ràng, ngắn gọn và thân thiện."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # 4. Gọi LLM
    llm = get_chat_model()
    response = await llm.ainvoke(messages)
    answer_text = str(response.content)

    logger.info(
        "[FAQ NODE] [OK] Đã sinh câu trả lời hoàn tất (độ dài: %d ký tự).", len(answer_text)
    )

    return {
        "messages": [response],
        "final_answer": answer_text,
    }


from app.ai.agent.fallback.nodes.fallback_node import fallback_node as central_fallback_node


async def fallback_faq_node(state: FAQState) -> dict[str, Any]:
    """
    Node 3: Xử lý Fallback khi không tìm thấy câu hỏi FAQ phù hợp.
    Tái sử dụng Central Fallback Hub (Zero-LLM Latency).
    """
    return await central_fallback_node(state)



# Alias tương thích ngược
faq_agent_node = generate_faq_node
faq_node = generate_faq_node

__all__ = [
    "retrieve_faq_node",
    "generate_faq_node",
    "fallback_faq_node",
    "faq_agent_node",
    "faq_node",
]
