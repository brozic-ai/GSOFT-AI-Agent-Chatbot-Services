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
from app.ai.rag.text.normalizer import VietnameseNormalizer
from app.core.config import settings
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retriever truy vấn ngữ cảnh Vector có phân quyền vai trò (User Roles RBAC) và Reranker."""

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
        top_k: int = 5,
        content_kind: str | None = None,
        user_roles: str | None = None,
        user_department: str | None = None,
    ) -> dict[str, Any]:
        """
        Thực hiện tìm kiếm ngữ cảnh có kiểm tra vai trò người dùng (user_roles) và Phòng ban (user_department).
        """
        effective_query = query
        if getattr(settings, "RAG_ENABLE_VIETNAMESE_NORMALIZATION", True) and query:
            effective_query = VietnameseNormalizer.normalize(
                query, expand_acronyms=True
            )

        logger.info(
            "[RAG] Retrieving context for query='%s' (normalized='%s'), roles='%s', dept='%s', top_k=%d",
            query,
            effective_query,
            user_roles,
            user_department,
            top_k,
        )

        # 1. Embed query thành vector 1024 chiều (có LRU Cache)
        query_embedding, cache_hit = await self.embedding_service.embed_query_cached(
            effective_query
        )
        logger.debug("[RAG] Query embedding hit_cache=%s", cache_hit)

        # 2. Xác định candidate_k (nếu dùng Reranker thực sự sẽ lấy nhiều candidates hơn)
        candidate_k = max(settings.HYBRID_TOP_K_CANDIDATES, top_k)

        # 3. Truy vấn CSDL Vector SQL Server có áp dụng bộ lọc phân quyền RBAC Vai trò + Phòng ban
        search_results = self.repository.search_vector_chunks(
            query=effective_query,
            query_embedding=query_embedding,
            top_k=candidate_k,
            content_kind=content_kind,
            user_roles=user_roles,
            user_department=user_department,
        )

        raw_docs = (
            search_results.get("documents", [[]])[0]
            if search_results.get("documents")
            else []
        )

        # 4. Rerank nếu có kết quả (dùng effective_query đã chuẩn hóa tiếng Việt & acronym)
        if raw_docs:
            ranked_indices = self.reranker.rerank(effective_query, raw_docs, top_k)
            # Lọc bớt danh sách theo 2D array format của SearchResponse
            results_filtered: dict[str, list[list[Any]]] = {}
            for key in ["ids", "documents", "metadatas", "distances", "citations"]:
                raw_list = (
                    search_results.get(key, [[]])[0] if search_results.get(key) else []
                )
                filtered_sub = [
                    raw_list[i] for i in ranked_indices if i < len(raw_list)
                ]
                results_filtered[key] = [filtered_sub]
            search_results = results_filtered

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
            "[OK] [RAG] Context retrieved: %d chunks found | Sources: %s",
            len(documents),
            sources,
        )

        return search_results
