"""
Factory function khởi tạo Reranker theo tham số cấu hình RERANKER_TYPE trong .env.
"""

from app.ai.rag.reranker.base import BaseReranker
from app.core.config import settings


def get_reranker() -> BaseReranker:
    """
    Factory tạo Reranker instance.
    - 'disabled': Passthrough (giữ nguyên thứ tự RRF, mặc định)
    - 'flashrank': Sử dụng FlashRank Reranker
    """
    if settings.RERANKER_TYPE == "flashrank":
        from app.ai.rag.reranker.flashrank_reranker import FlashRankReranker

        return FlashRankReranker()

    from app.ai.rag.reranker.disabled import DisabledReranker

    return DisabledReranker()
