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

# Ngưỡng RRF tối thiểu để coi là kết quả tin cậy (0.008 giúp cho phép Top 1-10 Vector-only đi qua)
_RRF_MIN_SCORE: float = 0.008


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
    faq_repo = None

    try:
        embedding_service = _get_embedding_service()
        faq_repo = _get_faq_repository()

        # 1. Tạo vector embedding cho câu truy vấn (có LRU cache)
        query_embedding, cache_hit = await embedding_service.embed_query_cached(query)
        logger.debug("[FAQ TOOL] Query embedding cache_hit=%s", cache_hit)

        # 2. Thực hiện Hybrid Search (Vector + FTS RRF) với ngưỡng Fallback
        results = faq_repo.search_faq_hybrid(
            query_embedding=query_embedding,
            query=query,
            top_k=top_k,
            rrf_min_score=_RRF_MIN_SCORE,
        )

        if not results:
            logger.info("[FAQ TOOL] Không tìm thấy FAQ nào vượt ngưỡng RRF cho query='%s'.", query[:80])
            return json.dumps(
                {"found": False, "faqs": [], "message": "Không tìm thấy thông tin FAQ phù hợp."},
                ensure_ascii=False,
            )

        # 3. Format kết quả rõ ràng cho LLM dễ hiểu
        faqs_formatted = []
        for i, r in enumerate(results, start=1):
            faqs_formatted.append({
                "rank": i,
                "question": r["question"],
                "answer": r["answer"],
                "confidence_score": round(r["rrf_score"], 5),
            })

        logger.info(
            "[FAQ TOOL] Tìm thấy %d FAQ cho query='%s' (top score=%.5f).",
            len(faqs_formatted),
            query[:80],
            results[0]["rrf_score"],
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
    finally:
        if faq_repo and hasattr(faq_repo, "db") and faq_repo.db:
            try:
                faq_repo.db.close()
            except Exception:
                pass


# Danh sách các tool sẽ được bind vào LLM trong faq_agent_node
FAQ_TOOLS = [search_faq_knowledge_base]

__all__ = ["search_faq_knowledge_base", "FAQ_TOOLS"]
