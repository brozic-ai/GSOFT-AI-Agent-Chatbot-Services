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


_langfuse_client = None


def get_langfuse_client() -> Optional[Any]:
    """Khởi tạo và trả về Langfuse client singleton."""
    global _langfuse_client
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

    if _langfuse_client is None:
        try:
            from langfuse import Langfuse

            os.environ["LANGFUSE_PUBLIC_KEY"] = pub_key
            os.environ["LANGFUSE_SECRET_KEY"] = sec_key
            os.environ["LANGFUSE_HOST"] = host
            os.environ["LANGFUSE_BASE_URL"] = host

            _langfuse_client = Langfuse(
                public_key=pub_key,
                secret_key=sec_key,
                host=host,
            )
            logger.info(
                "[LANGFUSE] Client initialized successfully for host='%s'", host
            )
        except Exception as ex:
            logger.warning("[LANGFUSE] Không thể khởi tạo Langfuse client: %s", ex)
            return None

    return _langfuse_client


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
    client = get_langfuse_client()
    if client is None:
        return None

    pub_key = settings.LANGFUSE_PUBLIC_KEY or os.getenv("LANGFUSE_PUBLIC_KEY", "")

    try:
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            from langfuse.callback import CallbackHandler

        # Chuẩn bị metadata sạch, loại bỏ None values
        clean_metadata = {
            k: v for k, v in (metadata or {}).items() if v is not None
        }
        if user_id:
            clean_metadata["langfuse_user_id"] = str(user_id)
        if session_id:
            clean_metadata["langfuse_session_id"] = str(session_id)
        if tags:
            clean_metadata["langfuse_tags"] = tags

        init_kwargs: Dict[str, Any] = {"public_key": pub_key}
        if user_id:
            init_kwargs["user_id"] = str(user_id)
        if session_id:
            init_kwargs["session_id"] = str(session_id)
        if tags:
            init_kwargs["tags"] = tags
        if trace_name:
            init_kwargs["trace_name"] = trace_name
        if version:
            init_kwargs["version"] = version

        # Thử khởi tạo với đầy đủ parameters, fallback an toàn nếu version cũ
        try:
            handler = CallbackHandler(**init_kwargs)
        except TypeError:
            try:
                handler = CallbackHandler(
                    public_key=pub_key,
                    session_id=str(session_id) if session_id else None,
                    user_id=str(user_id) if user_id else None,
                )
            except TypeError:
                handler = CallbackHandler(public_key=pub_key)

        return handler
    except ImportError:
        logger.debug(
            "[LANGFUSE] Thư viện 'langfuse' chưa được cài đặt. Bỏ qua Langfuse CallbackHandler."
        )
        return None
    except Exception as ex:
        logger.warning(
            "[LANGFUSE] Không thể khởi tạo Langfuse CallbackHandler: %s", ex
        )
        return None


def get_langfuse_langchain_config(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_name: Optional[str] = None,
    version: Optional[str] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo config dictionary chuẩn chỉnh nhất cho LangChain / LangGraph (invoke / ainvoke / astream).
    Tự động nhúng CallbackHandler và các metadata keys đặc thù của Langfuse (langfuse_user_id, langfuse_session_id, langfuse_tags).
    """
    effective_name = run_name or trace_name
    handler = get_langfuse_callback(
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        metadata=metadata,
        trace_name=effective_name,
        version=version,
    )
    callbacks = [handler] if handler else []

    clean_metadata = {k: v for k, v in (metadata or {}).items() if v is not None}
    if user_id:
        clean_metadata["langfuse_user_id"] = str(user_id)
        clean_metadata["user_id"] = str(user_id)
    if session_id:
        clean_metadata["langfuse_session_id"] = str(session_id)
        clean_metadata["session_id"] = str(session_id)
    if tags:
        clean_metadata["langfuse_tags"] = tags

    config: Dict[str, Any] = {
        "callbacks": callbacks,
        "metadata": clean_metadata,
    }
    if effective_name:
        config["run_name"] = effective_name
    if tags:
        config["tags"] = tags

    return config


def flush_langfuse() -> None:
    """Flush toàn bộ traces đang pending trước khi tắt ứng dụng hoặc kết thúc tác vụ."""
    global _langfuse_client
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception as ex:
            logger.debug("[LANGFUSE] Flush skipped: %s", ex)


