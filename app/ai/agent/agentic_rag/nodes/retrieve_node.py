"""
Retrieve Node cho RAG Fast Pipeline (app/ai/agent/agentic_rag/nodes/retrieve_node.py).
Truy xuất trực tiếp các chunks tài liệu thông qua Hybrid Search + BGE Cross-Encoder Reranker,
kết hợp Dynamic Top-K theo từng cấp độ Model (Low, Medium, High).
"""

import logging
from typing import Any

from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_context_params_for_level
from app.core.model_levels import normalize_model_level
from app.routers.dependencies import get_vector_retriever

logger = logging.getLogger(__name__)


async def retrieve_rag_node(state: AgenticRagState) -> dict[str, Any]:
    """
    Node 1 trong Fast Pipeline:
    Truy vấn Vector DB + Fulltext Search (RRF) kết hợp Cross-Encoder Reranker.
    Áp dụng dynamic top_k từ cấu hình của model_level tương ứng.
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
    model_level = (
        state.get("model_level", "medium")
        if isinstance(state, dict)
        else getattr(state, "model_level", "medium")
    ) or "medium"

    if not user_query and messages:
        for m in reversed(messages):
            if (
                hasattr(m, "content")
                and m.content
                and getattr(m, "type", "") in ("human", "user")
            ):
                user_query = str(m.content)
                break

    # Lấy thông số ngữ cảnh động cho model_level
    model_level = normalize_model_level(model_level)
    context_params = get_context_params_for_level(model_level)
    dynamic_top_k = context_params["top_k"]

    logger.info(
        "[RAG FAST-PIPELINE] Bắt đầu tra cứu (level=%s, top_k=%d) cho câu hỏi: '%s'",
        model_level,
        dynamic_top_k,
        str(user_query)[:80],
    )

    try:
        retriever = get_vector_retriever()
        results = await retriever.retrieve_context(
            query=state.get("retrieval_query") or user_query,
            top_k=dynamic_top_k,
            user_roles=user_roles,
            user_department=user_department,
        )

        docs = results.get("documents", [[]])[0] if results.get("documents") else []
        citations = (
            results.get("citations", [[]])[0] if results.get("citations") else []
        )

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

    except Exception:
        logger.exception("[RAG FAST-PIPELINE] Lỗi khi truy vấn retriever")
        return {
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "user_query": user_query,
        }
