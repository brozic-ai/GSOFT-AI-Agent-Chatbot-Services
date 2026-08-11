"""
Vector Retriever Subsystem cho RAG AI System (app/ai/rag/retrieval).

Chịu trách nhiệm truy vấn ngữ cảnh tài liệu và ép chặt quy tắc phân quyền người dùng (RBAC).
"""

import logging
from typing import Any

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retriever truy vấn ngữ cảnh Vector có phân quyền vai trò (User Roles RBAC)."""

    def __init__(
        self, repository: DocumentRepository, embedding_service: TeiEmbeddingService
    ):
        self.repository = repository
        self.embedding_service = embedding_service

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
        logger.info(
            "[RAG] Retrieving context for query='%s', roles='%s', dept='%s', top_k=%d",
            query,
            user_roles,
            user_department,
            top_k,
        )

        # 1. Embed query thành vector 1024 chiều (có LRU Cache)
        query_embedding, cache_hit = await self.embedding_service.embed_query_cached(
            query
        )
        logger.debug("[RAG] Query embedding hit_cache=%s", cache_hit)

        # 2. Truy vấn CSDL Vector SQL Server có áp dụng bộ lọc phân quyền RBAC Vai trò + Phòng ban
        search_results = self.repository.search_vector_chunks(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            content_kind=content_kind,
            user_roles=user_roles,
            user_department=user_department,
        )

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
