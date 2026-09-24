"""
Abstract Base Class cho phân hệ Reranker trong RAG System.
Tuân thủ Clean Architecture & Enterprise Standards.
"""

from abc import ABC, abstractmethod


class BaseReranker(ABC):
    """Interface chuẩn cho tất cả Reranker implementations."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[int]:
        """
        Rerank danh sách chunks theo query.

        Args:
            query: Câu hỏi / câu truy vấn tìm kiếm của người dùng.
            chunks: Danh sách chuỗi văn bản chunks thu thập từ Vector DB (RRF).
            top_k: Số lượng kết quả liên quan nhất cần trả về.

        Returns:
            Danh sách các vị trí index (0-indexed) của chunks đã sắp xếp giảm dần theo relevance score.
        """
        ...

    def rerank_with_scores(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """
        Rerank danh sách chunks theo query và trả về kèm relevance score.

        Args:
            query: Câu hỏi / câu truy vấn tìm kiếm của người dùng.
            chunks: Danh sách chuỗi văn bản chunks.
            top_k: Số lượng kết quả liên quan nhất cần trả về.

        Returns:
            Danh sách tuple: [(chunk_index, score), ...] sắp xếp giảm dần theo điểm liên quan.
        """
        ranked_indices = self.rerank(query, chunks, top_k)
        # Default mock scores nếu subclass không override
        return [(idx, 1.0 / (1.0 + rank)) for rank, idx in enumerate(ranked_indices)]

