"""
Disabled / Passthrough Reranker.
Mặc định khi RERANKER_TYPE=disabled — giữ nguyên thứ tự kết quả từ RRF Vector Search, không đòi hỏi thư viện bổ sung.
"""

from app.ai.rag.reranker.base import BaseReranker


class DisabledReranker(BaseReranker):
    """Passthrough reranker — giữ nguyên thứ tự từ RRF Fusion."""

    def rerank(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[int]:
        return list(range(min(top_k, len(chunks))))
