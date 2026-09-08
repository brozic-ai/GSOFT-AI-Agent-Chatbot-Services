"""
FAQ Retriever Service — Truy xuất ngữ cảnh FAQ tối ưu bằng Hybrid Search và Reranker.
Tái sử dụng TeiEmbeddingService và get_reranker từ RAG Core.
"""

import logging
from typing import Any

from app.ai.rag.reranker import get_reranker
from app.core.config import settings

logger = logging.getLogger(__name__)

# Ngưỡng tối thiểu của RRF (0.003 giúp bảo toàn các kết quả FTS-only rank 1-5)
_RRF_MIN_SCORE: float = 0.003

_embedding_service = None


def _get_embedding_service():
    """Lazy-initialize TeiEmbeddingService singleton."""
    global _embedding_service
    if _embedding_service is None:
        from app.ai.rag.embedding.service import TeiEmbeddingService

        _embedding_service = TeiEmbeddingService()
    return _embedding_service


def _get_faq_repository():
    """Tạo FaqRepository với DB session độc lập."""
    from app.core.database import SessionLocal
    from app.modules.faq_knowledge.repository import FaqRepository

    return FaqRepository(db=SessionLocal())


async def find_fast_faq_match(
    query: str,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """
    Tìm kiếm câu hỏi FAQ siêu tốc bằng Exact Match hoặc Vector Similarity cao (Zero-LLM Latency).
    - Exact match (100% khớp chuỗi sau chuẩn hóa Unicode): Độ trễ < 3ms.
    - Vector Similarity (>= threshold, mặc định 0.90 / 90%): Độ trễ ~20-50ms.
    Nếu tìm thấy, trả về ngay câu trả lời để hệ thống bỏ qua Classify Intent và RAG.
    Nếu không tìm thấy, trả về None để chuyển sang các bước phân loại thông thường.
    """
    if not getattr(settings, "FAQ_FAST_MATCH_ENABLED", True):
        return None

    query = (query or "").strip()
    if not query:
        return None

    faq_repo = None
    try:
        faq_repo = _get_faq_repository()

        # 1. Thử Exact Match trước (cực nhanh, không cần tính vector)
        exact_match = faq_repo.find_exact_match(query)
        if exact_match:
            logger.info(
                "[FAQ FAST-MATCH] [EXACT MATCH] Tìm thấy câu hỏi khớp 100%%: '%s' (faq_id=%s)",
                exact_match["question"],
                exact_match["faq_id"],
            )
            citation = {
                "source": f"FAQ: {exact_match['question']}",
                "page": None,
                "chunk_id": f"faq-{exact_match['faq_id']}",
                "score": 1.0,
                "faq_id": exact_match["faq_id"],
                "question": exact_match["question"],
                "answer": exact_match["answer"],
            }
            return {
                "found": True,
                "answer": exact_match["answer"],
                "question": exact_match["question"],
                "faq_id": exact_match["faq_id"],
                "score": 1.0,
                "match_type": "exact",
                "citations": [citation],
            }

        # 2. Thử Vector Similarity siêu gần (>= 90% / 0.90)
        target_threshold = threshold or getattr(settings, "FAQ_FAST_MATCH_THRESHOLD", 0.90)
        embed_svc = _get_embedding_service()
        query_embedding, _ = await embed_svc.embed_query_cached(query)

        vector_match = faq_repo.find_top_vector_similarity(
            query_embedding=query_embedding,
            min_similarity=target_threshold,
        )
        if vector_match:
            logger.info(
                "[FAQ FAST-MATCH] [VECTOR SIMILARITY >= %.2f] Khớp câu hỏi '%s' (faq_id=%s, score=%.4f)",
                target_threshold,
                vector_match["question"],
                vector_match["faq_id"],
                vector_match["score"],
            )
            citation = {
                "source": f"FAQ: {vector_match['question']}",
                "page": None,
                "chunk_id": f"faq-{vector_match['faq_id']}",
                "score": vector_match["score"],
                "faq_id": vector_match["faq_id"],
                "question": vector_match["question"],
                "answer": vector_match["answer"],
            }
            return {
                "found": True,
                "answer": vector_match["answer"],
                "question": vector_match["question"],
                "faq_id": vector_match["faq_id"],
                "score": vector_match["score"],
                "match_type": "vector_similarity",
                "citations": [citation],
            }

        return None

    except Exception as ex:
        logger.warning("[FAQ FAST-MATCH] Lỗi tra cứu FAQ fast-match: %s. Tiếp tục luồng thông thường.", ex)
        return None
    finally:
        if faq_repo and hasattr(faq_repo, "db") and faq_repo.db:
            try:
                faq_repo.db.close()
            except Exception:
                pass


async def retrieve_and_rerank_faqs(
    query: str,
    top_k: int = 3,
    candidate_count: int | None = None,
) -> dict[str, Any]:
    """
    Truy xuất và tái xếp hạng FAQ:
    1. Tạo embedding câu hỏi (có LRU cache).
    2. Hybrid Search (Vector + FTS RRF) lấy tập ứng viên Top N (mặc định 10-15).
    3. Rerank ngữ nghĩa sâu bằng Cross-Encoder (BAAI/bge-reranker hoặc FlashRank).
    4. Cắt Top K và chuẩn hoá danh sách Citations cho Frontend.
    """
    candidate_k = candidate_count or getattr(settings, "FAQ_SEARCH_CANDIDATES_K", 10)
    candidate_k = max(candidate_k, top_k)
    faq_repo = None

    try:
        embed_svc = _get_embedding_service()
        faq_repo = _get_faq_repository()

        # 1. Embed query (LRU cached)
        query_embedding, cache_hit = await embed_svc.embed_query_cached(query)
        logger.debug("[FAQ RETRIEVER] Query embedding cache_hit=%s", cache_hit)

        # 2. Hybrid RRF Search trên DB
        candidates = faq_repo.search_faq_hybrid(
            query_embedding=query_embedding,
            query=query,
            top_k=candidate_k,
            rrf_min_score=_RRF_MIN_SCORE,
        )

        if not candidates:
            logger.info("[FAQ RETRIEVER] Không tìm thấy ứng viên FAQ cho: '%s'", query[:80])
            return {"found": False, "faqs": [], "citations": []}

        # 3. Tái xếp hạng (Reranking)
        reranker = get_reranker()
        if hasattr(reranker, "rerank_with_scores") and len(candidates) > 1:
            candidate_texts = [
                f"Câu hỏi: {c['question']}\nCâu trả lời: {c['answer']}"
                for c in candidates
            ]
            ranked_pairs = reranker.rerank_with_scores(
                query=query,
                chunks=candidate_texts,
                top_k=top_k,
            )
            top_faqs = []
            for rank, (idx, score) in enumerate(ranked_pairs, start=1):
                if idx < len(candidates):
                    item = dict(candidates[idx])
                    item["rank"] = rank
                    item["confidence_score"] = round(float(score), 5)
                    top_faqs.append(item)
        else:
            top_faqs = [
                {**c, "rank": idx, "confidence_score": round(c.get("rrf_score", 0.0), 5)}
                for idx, c in enumerate(candidates[:top_k], start=1)
            ]

        # 4. Tạo Citations chuẩn cho Frontend SSE stream
        citations = [
            {
                "source": f"FAQ: {f['question']}",
                "page": None,
                "chunk_id": f"faq-{f.get('faq_id', idx)}",
                "score": f.get("confidence_score", 0.0),
                "faq_id": f.get("faq_id"),
                "question": f["question"],
                "answer": f["answer"],
            }
            for idx, f in enumerate(top_faqs, start=1)
        ]

        logger.info(
            "[FAQ RETRIEVER] [OK] Đã truy xuất & rerank %d FAQ (top score=%.5f).",
            len(top_faqs),
            top_faqs[0].get("confidence_score", 0.0) if top_faqs else 0.0,
        )

        return {
            "found": True,
            "faqs": top_faqs,
            "citations": citations,
        }

    except Exception as ex:
        logger.exception("[FAQ RETRIEVER] Lỗi truy xuất và rerank FAQ: %s", ex)
        return {"found": False, "faqs": [], "citations": [], "error": str(ex)}
    finally:
        if faq_repo and hasattr(faq_repo, "db") and faq_repo.db:
            try:
                faq_repo.db.close()
            except Exception:
                pass
