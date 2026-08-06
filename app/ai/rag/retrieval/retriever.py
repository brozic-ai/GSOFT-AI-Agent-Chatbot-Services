"""
Vector Retriever Subsystem cho RAG AI System (app/ai/rag/retrieval).

Chịu trách nhiệm truy vấn ngữ cảnh tài liệu và ép chặt quy tắc phân quyền người dùng (RBAC).
"""

import logging
from typing import List, Dict, Any, Optional

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retriever truy vấn ngữ cảnh Vector có phân quyền vai trò (User Roles RBAC)."""

    def __init__(self, repository: DocumentRepository, embedding_service: TeiEmbeddingService):
        self.repository = repository
        self.embedding_service = embedding_service

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        content_kind: Optional[str] = None,
        user_roles: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Thực hiện tìm kiếm ngữ cảnh có kiểm tra vai trò người dùng (user_roles).

        Args:
            query: Câu hỏi/truy vấn của người dùng.
            top_k: Số lượng chunk tối đa cần lấy.
            content_kind: Loại nội dung (instruction_text / image_ui_description).
            user_roles: Chuỗi danh sách vai trò người dùng (X-User-Roles) từ C# Gateway.

        Returns:
            Dict chứa danh sách chunks, metadatas, distances và citations.
        """
        logger.info("[RAG] Retrieving context for query='%s', roles='%s', top_k=%d", query, user_roles, top_k)

        # 1. Embed query thành vector 1024 chiều (có LRU Cache)
        query_embedding, cache_hit = await self.embedding_service.embed_query_cached(query)
        logger.debug("[RAG] Query embedding hit_cache=%s", cache_hit)

        # 2. Truy vấn CSDL Vector SQL Server có áp dụng bộ lọc phân quyền RBAC
        search_results = self.repository.search_vector_chunks(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            content_kind=content_kind,
            user_roles=user_roles,
        )

        return search_results
