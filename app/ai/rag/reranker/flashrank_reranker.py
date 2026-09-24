"""
FlashRank Reranker implementation (ms-marco-MiniLM-L-6-v2, ONNX, CPU).
Kích hoạt khi cài package `uv add flashrank` và đặt RERANKER_TYPE=flashrank trong .env.
"""

import logging

from app.ai.rag.reranker.base import BaseReranker

logger = logging.getLogger(__name__)


class FlashRankReranker(BaseReranker):
    """Sử dụng FlashRank ONNX CPU reranker để tính điểm liên quan giữa Query và Document Chunks."""

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-6-v2"):
        try:
            from flashrank import Ranker

            self._ranker = Ranker(model_name=model_name)
            logger.info(
                "[OK] FlashRankReranker initialized with model='%s'", model_name
            )
        except ImportError:
            logger.error(
                "[FAIL] Package 'flashrank' chưa được cài đặt. "
                "Hãy chạy 'uv add flashrank' hoặc đổi RERANKER_TYPE=disabled trong .env"
            )
            raise RuntimeError(
                "Package 'flashrank' chưa được cài đặt. Hãy chạy 'uv add flashrank'."
            )

    def rerank_with_scores(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        if not chunks:
            return []

        from flashrank import RerankRequest

        passages = [{"id": idx, "text": chunk} for idx, chunk in enumerate(chunks)]
        req = RerankRequest(query=query, passages=passages)
        results = self._ranker.rerank(req)

        top_results = [
            (
                int(item["id"]) if "id" in item else item.get("index", idx),
                float(item.get("score", 0.0)),
            )
            for idx, item in enumerate(results[:top_k])
        ]
        return top_results

    def rerank(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[int]:
        if not chunks:
            return []

        results = self.rerank_with_scores(query, chunks, top_k)
        return [idx for idx, _ in results]

