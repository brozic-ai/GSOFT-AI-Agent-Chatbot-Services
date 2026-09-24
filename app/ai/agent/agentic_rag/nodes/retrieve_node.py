"""
Retrieve Node cho RAG Fast Pipeline (app/ai/agent/agentic_rag/nodes/retrieve_node.py).
Truy xuất trực tiếp các chunks tài liệu thông qua Hybrid Search + BGE Cross-Encoder Reranker,
loại bỏ hoàn toàn LLM Grader và Agent tool overhead để đạt độ trễ tối ưu 2-3s.
"""

import logging
from typing import Any, Dict

from app.ai.agent.agentic_rag.state import AgenticRagState
from app.routers.dependencies import get_vector_retriever

logger = logging.getLogger(__name__)


async def retrieve_rag_node(state: AgenticRagState) -> Dict[str, Any]:
    """
    Node 1 trong Fast Pipeline:
    Truy vấn Vector DB + Fulltext Search (RRF) kết hợp Cross-Encoder Reranker.
    """
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    user_roles = (
        state.get("user_roles")
        if isinstance(state, dict)
        else getattr(state, "user_roles", None)
    )
    user_department = (
        state.get("user_department")
        if isinstance(state, dict)
        else getattr(state, "user_department", None)
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

    logger.info("[RAG FAST-PIPELINE] Bắt đầu tra cứu tri thức cho câu hỏi: '%s'", str(user_query)[:80])

    try:
        retriever = get_vector_retriever()
        results = await retriever.retrieve_context(
            query=user_query,
            top_k=None,  # Dynamic Top-K theo phân loại câu hỏi (Specific=3-5, Exhaustive=10-15)
            user_roles=user_roles,
            user_department=user_department,
        )

        docs = results.get("documents", [[]])[0] if results.get("documents") else []
        citations = results.get("citations", [[]])[0] if results.get("citations") else []

        logger.info(
            "[RAG FAST-PIPELINE] Tra cứu hoàn tất: %d chunks tài liệu trúng khớp sau Cross-Encoder Reranker.",
            len(docs),
        )

        return {
            "documents": docs,
            "citations": citations,
            "is_relevant": len(docs) > 0,
            "user_query": user_query,
        }

    except Exception as ex:
        logger.error("[RAG FAST-PIPELINE] Lỗi khi truy vấn retriever: %s", ex, exc_info=True)
        return {
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "user_query": user_query,
        }
