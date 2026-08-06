"""
Dịch vụ TEI (Text Embeddings Inference) Service.

Đóng vai trò làm Client kết nối với máy chủ TEI (hỗ trợ mô hình bge-m3, 1024 chiều),
tích hợp bộ nhớ cache LRU cho các câu truy vấn (Query Embedding Cache) để tối ưu hiệu năng.
"""

import logging
from typing import List, Tuple
import httpx
from cachetools import TTLCache

from app.core.config import settings

logger = logging.getLogger(__name__)

# LRU Cache cho Query Embeddings (tối đa 1,024 câu truy vấn, TTL 1 giờ)
_QUERY_EMBEDDING_CACHE: TTLCache = TTLCache(maxsize=1024, ttl=3600)


class TeiEmbeddingService:
    """Service tạo Vector Embeddings thông qua TEI Server."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.TEI_URL).rstrip("/")
        self.embed_url = f"{self.base_url}/embed"

    async def embed_texts(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
        """
        Tạo embeddings cho danh sách đoạn văn bản (Ingestion Batch).
        Tự động chia nhỏ thành các mini-batch (mặc định 16 chunks/batch) để tránh lỗi 413 Payload Too Large từ TEI Server.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    response = await client.post(
                        self.embed_url,
                        json={"inputs": batch},
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                    embeddings = response.json()
                    all_embeddings.extend(embeddings)
                return all_embeddings
            except Exception as ex:
                logger.error("[FAIL] Error calling TEI Server embed_texts: %s", ex, exc_info=True)
                raise ex

    async def embed_query(self, query: str) -> List[float]:
        """
        Tạo embedding cho 1 câu truy vấn của người dùng.
        """
        res = await self.embed_texts([query])
        if res and len(res) > 0:
            return res[0]
        raise ValueError("TEI Server returned empty embedding for query.")

    async def embed_query_cached(self, query: str) -> Tuple[List[float], bool]:
        """
        Tạo embedding cho câu truy vấn có sử dụng Cache.
        Trả về: (embedding_vector, cache_hit_boolean)
        """
        cache_key = query.strip()
        if cache_key in _QUERY_EMBEDDING_CACHE:
            logger.debug("[CACHE HIT] Query embedding retrieved from cache.")
            return _QUERY_EMBEDDING_CACHE[cache_key], True

        embedding = await self.embed_query(query)
        _QUERY_EMBEDDING_CACHE[cache_key] = embedding
        return embedding, False
