"""
Langfuse LLMOps Tracing Integration.

Tuân thủ best practices của Langfuse:
- Sử dụng native LangChain / LangGraph CallbackHandler
- Hỗ trợ tracking session_id (nhóm hội thoại), user_id (phân quyền / chi phí theo user)
- Gán tags, metadata (user_roles, user_department, provider) phục vụ lọc và phân tích
- Tự động flush sự kiện và fallback an toàn khi chưa cấu hình keys hoặc tắt tính năng
"""

import logging
import os
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_langfuse_configured() -> bool:
    """Kiểm tra xem Langfuse có được bật và cấu hình đầy đủ keys hay không."""
    if not getattr(settings, "LANGFUSE_ENABLED", True):
        return False
    pub_key = settings.LANGFUSE_PUBLIC_KEY or os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec_key = settings.LANGFUSE_SECRET_KEY or os.getenv("LANGFUSE_SECRET_KEY", "")
    return bool(pub_key and sec_key)


def get_langfuse_callback(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_name: Optional[str] = None,
    version: Optional[str] = None,
) -> Any:
    """
    Tạo LangChain / LangGraph CallbackHandler cho Langfuse.

    Args:
        user_id: ID của người dùng (dùng cho user attribution, cost per user).
        session_id: ID của phiên chat (dùng để nhóm luồng hội thoại nhiều lượt).
        tags: Danh sách nhãn phân loại (vd: ["rag", "chat", "streaming"]).
        metadata: Dữ liệu bổ sung (user_roles, user_department, v.v.).
        trace_name: Tên trace mô tả ngắn gọn (vd: "Chatbot-RAG: Tra cứu quy trình").
        version: Phiên bản ứng dụng / prompt (nếu có).

    Returns:
        Instance của CallbackHandler nếu cấu hình thành công, ngược lại None.
    """
    if not getattr(settings, "LANGFUSE_ENABLED", True):
        return None

    pub_key = settings.LANGFUSE_PUBLIC_KEY or os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec_key = settings.LANGFUSE_SECRET_KEY or os.getenv("LANGFUSE_SECRET_KEY", "")
    host = (
        settings.LANGFUSE_BASE_URL
        or settings.LANGFUSE_HOST
        or os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or "http://localhost:3000"
    )

    if not pub_key or not sec_key:
        return None

    try:
        from langfuse.callback import CallbackHandler

        # Chuẩn bị metadata sạch, loại bỏ None values
        clean_metadata = {k: v for k, v in (metadata or {}).items() if v is not None}

        handler = CallbackHandler(
            public_key=pub_key,
            secret_key=sec_key,
            host=host,
            user_id=str(user_id) if user_id else None,
            session_id=str(session_id) if session_id else None,
            tags=tags or ["bvbank-chatbot"],
            metadata=clean_metadata,
            trace_name=trace_name,
            version=version,
        )
        return handler
    except ImportError:
        logger.debug("[LANGFUSE] Thư viện 'langfuse' chưa được cài đặt. Bỏ qua Langfuse CallbackHandler.")
        return None
    except Exception as ex:
        logger.warning("[LANGFUSE] Không thể khởi tạo Langfuse CallbackHandler: %s", ex)
        return None


def flush_langfuse() -> None:
    """Flush toàn bộ traces đang pending trước khi tắt ứng dụng hoặc kết thúc tác vụ."""
    try:
        import langfuse
        if hasattr(langfuse, "flush"):
            langfuse.flush()
    except Exception as ex:
        logger.debug("[LANGFUSE] Flush skipped: %s", ex)
