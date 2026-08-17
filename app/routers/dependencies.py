"""
Dependency Injection Container tổng cho toàn bộ ứng dụng (App DI Container).

Cung cấp các hàm getter (FastAPI Depends) để inject service/repository
vào các route handler một cách nhất quán, dễ duy trì và dễ test (Clean Architecture).
"""

import logging

from typing import Optional
from fastapi import Header, HTTPException, status
from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.core.config import Settings, get_settings
from app.llmops.factory import get_chat_model
from app.modules.chat.service import ChatService
from app.modules.chat.repository import ChatRepository
from app.modules.document.repository import DocumentRepository
from app.modules.document.service import DocumentService

logger = logging.getLogger(__name__)


# 0. User Identity Dependency
def require_user_id(x_user_id: Optional[str] = Header(None, alias="X-User-Id")) -> str:
    """Dependency bắt buộc có X-User-Id hợp lệ từ Gateway, trả 401 Unauthorized nếu thiếu."""
    clean_id = str(x_user_id or "").strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or empty X-User-Id header.",
        )
    return clean_id


# 1. Settings Dependency
def get_settings_dep() -> Settings:
    """FastAPI Dependency trả về Settings instance."""
    return get_settings()


# 2. LLM Provider Dependency
_llm_provider_cache: BaseChatModel | None = None


def get_llm_provider_dep() -> BaseChatModel:
    """Trả về LLM provider singleton dựa trên AI_PROVIDER trong .env."""
    global _llm_provider_cache
    if _llm_provider_cache is None:
        _llm_provider_cache = get_chat_model()
        logger.info(
            "[OK] LLM Provider initialized: %s", type(_llm_provider_cache).__name__
        )
    return _llm_provider_cache


# 3. Database Connection Session Dependency
def get_db_dep():
    """FastAPI Dependency trả về SQLAlchemy Session cho từng request."""
    from app.core.database import get_db

    yield from get_db()


# 4. Document Repository Dependency
_document_repository_cache: DocumentRepository | None = None


def get_repository() -> DocumentRepository:
    """FastAPI Dependency trả về DocumentRepository instance."""
    global _document_repository_cache
    if _document_repository_cache is None:
        _document_repository_cache = DocumentRepository()
        logger.info("[OK] DocumentRepository initialized with ORM SessionLocal.")
    return _document_repository_cache


# 5. TEI Embedding Service Dependency
_tei_embedding_cache: TeiEmbeddingService | None = None


def get_embedding_service() -> TeiEmbeddingService:
    """FastAPI Dependency trả về TeiEmbeddingService instance."""
    global _tei_embedding_cache
    if _tei_embedding_cache is None:
        _tei_embedding_cache = TeiEmbeddingService()
        logger.info("[OK] TeiEmbeddingService initialized.")
    return _tei_embedding_cache


# 6. Vector Retriever Dependency
def get_vector_retriever() -> VectorRetriever:
    """FastAPI Dependency trả về VectorRetriever hỗ trợ phân quyền RBAC và Reranker."""
    from app.ai.rag.reranker import get_reranker

    repo = get_repository()
    embed_svc = get_embedding_service()
    reranker = get_reranker()
    return VectorRetriever(
        repository=repo, embedding_service=embed_svc, reranker=reranker
    )


# 7. Document Business Service Dependency
def get_document_service() -> DocumentService:
    """FastAPI Dependency trả về DocumentService instance."""
    repo = get_repository()
    embed_svc = get_embedding_service()
    return DocumentService(repository=repo, embedding_service=embed_svc)


# 8. Chat Repository Dependency
_chat_repository_cache: ChatRepository | None = None


def get_chat_repository() -> ChatRepository:
    """FastAPI Dependency trả về ChatRepository singleton instance."""
    global _chat_repository_cache
    if _chat_repository_cache is None:
        _chat_repository_cache = ChatRepository()
        logger.info("[OK] ChatRepository initialized with ORM SessionLocal.")
    return _chat_repository_cache


# 9. Chat Business Service Dependency
def get_chat_service() -> ChatService:
    """FastAPI Dependency trả về ChatService instance."""
    retriever = get_vector_retriever()
    llm = get_llm_provider_dep()
    chat_repo = get_chat_repository()
    return ChatService(retriever=retriever, llm_provider=llm, chat_repository=chat_repo)


# Lifecycle helper — gọi bởi lifespan.py khi shutdown
def _reset_caches() -> None:
    """Reset tất cả singleton cache khi shutdown."""
    global _llm_provider_cache, _document_repository_cache, _tei_embedding_cache, _chat_repository_cache
    _llm_provider_cache = None
    _document_repository_cache = None
    _tei_embedding_cache = None
    _chat_repository_cache = None
    logger.info("[DONE] Dependency caches cleared.")
