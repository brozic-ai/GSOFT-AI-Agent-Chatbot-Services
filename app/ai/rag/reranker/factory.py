"""
Factory function khởi tạo Reranker theo tham số cấu hình RERANKER_TYPE trong .env.
"""

from app.ai.rag.reranker.base import BaseReranker
from app.core.config import settings


def get_reranker(reranker_type: str | None = None, model_name: str | None = None) -> BaseReranker:
    """
    Factory tạo Reranker instance theo cấu hình hoặc tham số truyền vào.
    - 'bge' / 'cross_encoder': Sử dụng CrossEncoderReranker (SentenceTransformers, BAAI/bge-reranker-base)
    - 'flashrank': Sử dụng FlashRank Reranker
    - 'disabled': Passthrough (giữ nguyên thứ tự RRF, mặc định)
    """
    target_type = (reranker_type or settings.RERANKER_TYPE or "disabled").lower()
    target_model = model_name or getattr(settings, "RERANKER_MODEL", "BAAI/bge-reranker-base")

    if target_type in ("bge", "cross_encoder", "crossencoder"):
        from app.ai.rag.reranker.cross_encoder_reranker import CrossEncoderReranker

        return CrossEncoderReranker(model_name=target_model)

    if target_type == "flashrank":
        from app.ai.rag.reranker.flashrank_reranker import FlashRankReranker

        return FlashRankReranker(model_name=target_model)

    from app.ai.rag.reranker.disabled import DisabledReranker

    return DisabledReranker()

