"""
Vector Retriever Subsystem cho RAG AI System (app/ai/rag/retrieval).

Chịu trách nhiệm truy vấn ngữ cảnh tài liệu, ép chặt quy tắc phân quyền người dùng (RBAC)
và áp dụng Reranking linh hoạt (DisabledReranker / FlashRankReranker).
"""

import logging
from typing import Any, Dict, List, Optional

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.reranker.base import BaseReranker
from app.ai.rag.reranker.disabled import DisabledReranker
from app.ai.rag.retrieval.query_analyzer import determine_dynamic_top_k
from app.ai.rag.text.normalizer import VietnameseNormalizer
from app.core.config import settings
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retriever truy vấn ngữ cảnh Vector có phân quyền vai trò (User Roles RBAC), Dynamic Top-K và Reranker."""

    def __init__(
        self,
        repository: DocumentRepository,
        embedding_service: TeiEmbeddingService,
        reranker: BaseReranker | None = None,
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.reranker = reranker or DisabledReranker()

    async def retrieve_context(
        self,
        query: str,
        top_k: int | None = None,
        content_kind: str | None = None,
        user_roles: str | None = None,
        user_department: str | None = None,
    ) -> dict[str, Any]:
        """
        Thực hiện tìm kiếm ngữ cảnh có Dynamic Top-K, kiểm tra vai trò người dùng (user_roles) và Phòng ban (user_department).
        
        Quy tắc Dynamic Top-K:
        - Specific query (hỏi đích danh 1 người, 1 con số, 1 định nghĩa, 1 nút) -> Top-K nhỏ (3-5)
        - Exhaustive query (hỏi "tất cả", "liệt kê", "có những gì", "các loại") -> Top-K lớn (10-15)
        - Áp dụng Same-Document/Section Expansion khi câu hỏi mang tính liệt kê để không bỏ sót các bước.
        - Chạy Reranking và chỉ gửi đúng Top-K tối ưu tới LLM Context Builder.
        """
        # 1. Tính toán Dynamic Top-K dựa trên ý định & đặc tính câu hỏi
        effective_top_k, analysis = determine_dynamic_top_k(query, requested_top_k=top_k)
        is_exhaustive = analysis.is_exhaustive

        effective_query = query
        if getattr(settings, "RAG_ENABLE_VIETNAMESE_NORMALIZATION", True) and query:
            effective_query = VietnameseNormalizer.normalize(
                query, expand_acronyms=True
            )

        logger.info(
            "[RAG DYNAMIC TOP-K] Query='%s' (type=%s, is_exhaustive=%s) -> Top-K: %d | roles='%s', dept='%s'",
            query[:80],
            analysis.category.value,
            is_exhaustive,
            effective_top_k,
            user_roles,
            user_department,
        )

        # 2. Embed query thành vector 1024 chiều (có LRU Cache)
        query_embedding, cache_hit = await self.embedding_service.embed_query_cached(
            effective_query
        )
        logger.debug("[RAG] Query embedding hit_cache=%s", cache_hit)

        # 3. Xác định candidate_k (thu thập đủ ứng viên trước khi rerank)
        candidate_multiplier = getattr(settings, "RAG_CANDIDATE_MULTIPLIER", 3)
        candidate_k = max(
            settings.HYBRID_TOP_K_CANDIDATES,
            effective_top_k * candidate_multiplier
        )
        if is_exhaustive:
            candidate_k = max(candidate_k, effective_top_k * 4)

        # 4. Truy vấn CSDL Vector SQL Server (Hybrid Search Vector + FTS + RBAC)
        search_results = self.repository.search_vector_chunks(
            query=effective_query,
            query_embedding=query_embedding,
            top_k=candidate_k,
            content_kind=content_kind,
            user_roles=user_roles,
            user_department=user_department,
        )

        raw_ids = search_results.get("ids", [[]])[0] if search_results.get("ids") else []
        raw_docs = search_results.get("documents", [[]])[0] if search_results.get("documents") else []
        raw_metas = search_results.get("metadatas", [[]])[0] if search_results.get("metadatas") else []
        raw_dists = search_results.get("distances", [[]])[0] if search_results.get("distances") else []
        raw_cits = search_results.get("citations", [[]])[0] if search_results.get("citations") else []

        # 5. Mở rộng ngữ cảnh cùng Phân đoạn / Sibling Chunks khi câu hỏi mang tính liệt kê (Exhaustive)
        if is_exhaustive and raw_metas:
            existing_ids = set(raw_ids)
            # Gom nhóm các chunk_index theo backend_id từ top 5 candidates
            doc_chunk_map: dict[str, list[int]] = {}
            for m in raw_metas[:6]:
                bid = str(m.get("backend_id") or m.get("backendId") or m.get("backend_document_id") or "")
                c_idx = m.get("chunk_index")
                if bid and c_idx is not None:
                    try:
                        c_int = int(c_idx)
                        if bid not in doc_chunk_map:
                            doc_chunk_map[bid] = []
                        doc_chunk_map[bid].append(c_int)
                    except (ValueError, TypeError):
                        pass

            # Lấy các chunk liền kề để không bỏ sót các bước quy trình
            for bid, indices in doc_chunk_map.items():
                if len(indices) >= 2:
                    adjacent = self.repository.get_adjacent_chunks(bid, indices)
                    for adj in adjacent:
                        adj_id = adj["id"]
                        if adj_id not in existing_ids:
                            existing_ids.add(adj_id)
                            raw_ids.append(adj_id)
                            raw_docs.append(adj["document"])
                            raw_metas.append(adj["metadata"])
                            raw_dists.append(1.0)
                            raw_cits.append({
                                "source": adj["metadata"].get("source"),
                                "page": adj["metadata"].get("page") or adj["metadata"].get("slide"),
                                "chunk_id": adj_id,
                                "score": 0.5,
                            })

        # 6. Rerank kết quả và chỉ giữ lại Top-K tinh hoa nhất gửi tới LLM
        if raw_docs:
            rerank_k = getattr(settings, "RERANKER_TOP_K", 4)
            if is_exhaustive:
                rerank_k = max(rerank_k, min(effective_top_k, rerank_k * 2))
            else:
                rerank_k = min(effective_top_k, rerank_k)

            if hasattr(self.reranker, "rerank_with_scores"):
                scored_results = self.reranker.rerank_with_scores(
                    effective_query, raw_docs, rerank_k
                )
                ranked_indices = [idx for idx, _ in scored_results]
                for idx, sc in scored_results:
                    if idx < len(raw_cits) and isinstance(raw_cits[idx], dict):
                        raw_cits[idx]["score"] = round(sc, 4)
            else:
                ranked_indices = self.reranker.rerank(
                    effective_query, raw_docs, rerank_k
                )

            # Lọc danh sách theo ranked_indices
            filtered_ids = [raw_ids[i] for i in ranked_indices if i < len(raw_ids)]
            filtered_docs = [raw_docs[i] for i in ranked_indices if i < len(raw_docs)]
            filtered_metas = [raw_metas[i] for i in ranked_indices if i < len(raw_metas)]
            filtered_dists = [raw_dists[i] for i in ranked_indices if i < len(raw_dists)]
            filtered_cits = [raw_cits[i] for i in ranked_indices if i < len(raw_cits)]

            search_results = {
                "ids": [filtered_ids],
                "documents": [filtered_docs],
                "metadatas": [filtered_metas],
                "distances": [filtered_dists],
                "citations": [filtered_cits],
                "query_analysis": {
                    "category": analysis.category.value,
                    "recommended_top_k": rerank_k,
                    "is_exhaustive": is_exhaustive,
                    "reasoning": analysis.reasoning,
                }
            }

        documents = (
            search_results.get("documents", [[]])[0]
            if search_results.get("documents")
            else []
        )
        citations = (
            search_results.get("citations", [[]])[0]
            if search_results.get("citations")
            else []
        )
        sources = list(
            dict.fromkeys(
                c.get("source")
                for c in citations
                if isinstance(c, dict) and c.get("source")
            )
        )
        logger.info(
            "[OK] [RAG DYNAMIC] Context retrieved: %d chunks found (Target Top-K=%d) | Sources: %s",
            len(documents),
            effective_top_k,
            sources,
        )

        return search_results

