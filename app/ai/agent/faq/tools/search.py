"""
FAQ Search Tool — Công cụ tìm kiếm FAQ Knowledge Base bằng Hybrid Search (RRF).

Tool này được LLM gọi thông qua cơ chế Tool Calling của LangGraph ReAct pattern.
Tái sử dụng TeiEmbeddingService và FaqRepository.search_faq_hybrid() từ hệ thống RAG.
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Module-level singletons (lazy-initialized)
_embedding_service = None
_faq_repository = None

# Ngưỡng RRF tối thiểu để coi là kết quả tin cậy (0.003 cho phép cả FTS-only rank 1-5 đi qua RRF)
_RRF_MIN_SCORE: float = 0.003


def _get_embedding_service():
    """Lazy-initialize TeiEmbeddingService (module-level singleton)."""
    global _embedding_service
    if _embedding_service is None:
        from app.ai.rag.embedding.service import TeiEmbeddingService
        _embedding_service = TeiEmbeddingService()
    return _embedding_service


def _get_faq_repository():
    """Tạo FaqRepository với DB session độc lập cho mỗi lượt gọi."""
    from app.core.database import SessionLocal
    from app.modules.faq_knowledge.repository import FaqRepository
    return FaqRepository(db=SessionLocal())


class SearchFaqInput(BaseModel):
    query: str = Field(
        description=(
            "Câu hỏi đầy đủ của người dùng cần tra cứu trong Cơ sở dữ liệu FAQ. "
            "Nên là câu hỏi tự nhiên, đầy đủ ngữ nghĩa (không cắt bớt)."
        )
    )
    top_k: int = Field(
        default=3,
        description="Số lượng FAQ phù hợp nhất cần trả về (mặc định 3, tối đa 5).",
    )


@tool("search_faq_knowledge_base", args_schema=SearchFaqInput)
async def search_faq_knowledge_base(query: str, top_k: int = 3) -> str:
    """Tìm kiếm trong Cơ sở dữ liệu câu hỏi thường gặp (FAQ Knowledge Base) của BVBank.

    Dùng tool này khi người dùng hỏi về quy trình thủ tục, hotline, giờ làm việc,
    thông tin liên hệ, hướng dẫn sử dụng hệ thống, chính sách nội bộ đơn giản hoặc
    bất kỳ câu hỏi có thể đã được chuẩn bị sẵn câu trả lời chuẩn.

    KHÔNG dùng tool này để tra cứu các tài liệu văn bản phức tạp, quy chế chi tiết
    nhiều trang — hãy dùng search_policy_and_manual_docs cho các trường hợp đó.
    """
    top_k = max(1, min(top_k, 5))
    try:
        from app.ai.agent.faq.services.faq_retriever import retrieve_and_rerank_faqs

        retrieval_res = await retrieve_and_rerank_faqs(query=query, top_k=top_k)
        if not retrieval_res.get("found"):
            logger.info("[FAQ TOOL] Không tìm thấy FAQ nào cho query='%s'.", query[:80])
            return json.dumps(
                {"found": False, "faqs": [], "message": "Không tìm thấy thông tin FAQ phù hợp."},
                ensure_ascii=False,
            )

        faqs_formatted = [
            {
                "rank": f["rank"],
                "question": f["question"],
                "answer": f["answer"],
                "confidence_score": f["confidence_score"],
            }
            for f in retrieval_res.get("faqs", [])
        ]

        logger.info(
            "[FAQ TOOL] Tìm thấy %d FAQ đã rerank cho query='%s' (top score=%.5f).",
            len(faqs_formatted),
            query[:80],
            faqs_formatted[0]["confidence_score"] if faqs_formatted else 0.0,
        )
        return json.dumps(
            {"found": True, "faqs": faqs_formatted},
            ensure_ascii=False,
        )

    except Exception as ex:
        logger.exception("[FAQ TOOL] Lỗi search_faq_knowledge_base: %s", ex)
        return json.dumps(
            {"found": False, "faqs": [], "error": str(ex)},
            ensure_ascii=False,
        )


# Danh sách các tool sẽ được bind vào LLM trong faq_agent_node
FAQ_TOOLS = [search_faq_knowledge_base]

__all__ = ["search_faq_knowledge_base", "FAQ_TOOLS"]
