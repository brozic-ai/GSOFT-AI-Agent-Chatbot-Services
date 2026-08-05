"""
Dependency Injection Container tổng cho toàn bộ ứng dụng.

Cung cấp các hàm getter (FastAPI Depends) để inject service/repository
vào các route handler một cách nhất quán và dễ test.

Kiến trúc DI:
    Config (settings)
        └── LLM Provider (BaseChatModel)
        └── Database Connection (pyodbc cursor) ← TODO: implement core/database.py
        └── Services (Chat, Document, ...) ← inject provider + repo
"""

import logging
from typing import Generator

from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings, get_settings, Settings
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


# 1. Settings Dependency
def get_settings_dep() -> Settings:
    """
    FastAPI Dependency trả về Settings instance.

    Ví dụ:
        @router.get("/info")
        async def info(cfg: Settings = Depends(get_settings_dep)):
            return {"project": cfg.PROJECT_NAME}
    """
    return get_settings()


# 2. LLM Provider Dependency
_llm_provider_cache: BaseChatModel | None = None


def get_llm_provider_dep() -> BaseChatModel:
    """
    Trả về LLM provider singleton dựa trên AI_PROVIDER trong .env.
    Provider được cache sau lần khởi tạo đầu tiên.

    Ví dụ:
        @router.post("/chat")
        async def chat(llm: BaseChatModel = Depends(get_llm_provider_dep)):
            result = llm.invoke(...)
    """
    global _llm_provider_cache
    if _llm_provider_cache is None:
        _llm_provider_cache = get_chat_model()
        logger.info("[OK] LLM Provider initialized: %s", type(_llm_provider_cache).__name__)
    return _llm_provider_cache


# 3. Database Connection Dependency
def get_db_dep():
    """
    FastAPI Dependency trả về SQLAlchemy Session cho từng request (auto-close sau request).
    """
    from app.core.database import get_db

    yield from get_db()


# 4. Module-specific Service Dependencies
# Các dependency dưới đây sẽ được bổ sung khi implement từng module.

# --- Chat Module ---
# TODO: Uncomment khi implement chat module
#
# from app.modules.chat.service import ChatService
# _chat_service_cache: ChatService | None = None
#
# def get_chat_service() -> ChatService:
#     global _chat_service_cache
#     if _chat_service_cache is None:
#         llm = get_llm_provider_dep()
#         _chat_service_cache = ChatService(llm_provider=llm)
#     return _chat_service_cache

# --- Document / Ingestion Module ---
# TODO: Uncomment khi implement document module
#
# from app.modules.document.service import DocumentService
# _document_service_cache: DocumentService | None = None
#
# def get_document_service() -> DocumentService:
#     global _document_service_cache
#     if _document_service_cache is None:
#         _document_service_cache = DocumentService(
#             connection_string=settings.SQLSERVER_CONNECTIONSTRING,
#         )
#     return _document_service_cache


# Lifecycle helper — gọi bởi lifespan.py khi shutdown
def _reset_caches() -> None:
    """Reset tất cả singleton cache. Gọi khi shutdown."""
    global _llm_provider_cache
    _llm_provider_cache = None
    logger.info("[DONE] Dependency caches cleared.")
