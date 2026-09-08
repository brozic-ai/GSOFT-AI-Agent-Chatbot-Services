"""
Cross-Encoder Reranker hỗ trợ đa ngôn ngữ và tiếng Việt (BGE Reranker).
Sử dụng `sentence_transformers.CrossEncoder` với mô hình BAAI/bge-reranker-base hoặc BAAI/bge-reranker-v2-m3.
"""

import logging
from typing import ClassVar

from app.ai.rag.reranker.base import BaseReranker

logger = logging.getLogger(__name__)


class CrossEncoderReranker(BaseReranker):
    """
    Reranker dựa trên kiến trúc Cross-Encoder (SentenceTransformers).
    Tối ưu cho tiếng Việt và truy xuất thông tin ngân hàng đa ngôn ngữ.
    """

    _model_cache: ClassVar[dict[str, object]] = {}

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        self.model_name = model_name
        self._model = self._get_or_load_model(model_name)

    @classmethod
    def _get_or_load_model(cls, model_name: str) -> object:
        """Cache model singleton trên bộ nhớ để tránh load lại nhiều lần."""
        if model_name not in cls._model_cache:
            try:
                from sentence_transformers import CrossEncoder

                logger.info("[RERANKER] Đang tải mô hình Cross-Encoder: %s ...", model_name)
                model = CrossEncoder(model_name)
                cls._model_cache[model_name] = model
                logger.info("[RERANKER] [OK] Đã tải thành công Cross-Encoder: %s", model_name)
            except Exception as ex:
                logger.error(
                    "[RERANKER] [FAIL] Không thể tải mô hình Cross-Encoder '%s': %s",
                    model_name,
                    ex,
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Không thể khởi tạo CrossEncoderReranker với model '{model_name}': {ex}"
                ) from ex
        return cls._model_cache[model_name]

    def rerank_with_scores(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """
        Dự đoán điểm số liên quan giữa Query và từng Chunk.
        Trả về danh sách tuple (vị trí gốc, điểm số Cross-Encoder) đã sort giảm dần.
        """
        if not chunks:
            return []

        if not query or not query.strip():
            return [(idx, 0.0) for idx in range(min(top_k, len(chunks)))]

        try:
            pairs = [[query, chunk] for chunk in chunks]
            scores = self._model.predict(pairs)  # type: ignore[attr-defined]

            indexed_scores = [(idx, float(score)) for idx, score in enumerate(scores)]
            indexed_scores.sort(key=lambda x: x[1], reverse=True)
            return indexed_scores[:top_k]
        except Exception as ex:
            logger.warning(
                "[RERANKER] Lỗi dự đoán Cross-Encoder (%s). Fallback về thứ tự gốc.", ex
            )
            return [(idx, 1.0 / (1.0 + idx)) for idx in range(min(top_k, len(chunks)))]

    def rerank(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[int]:
        """Trả về danh sách chỉ số (0-indexed) của top_k chunks liên quan nhất."""
        results = self.rerank_with_scores(query, chunks, top_k)
        return [idx for idx, _ in results]
