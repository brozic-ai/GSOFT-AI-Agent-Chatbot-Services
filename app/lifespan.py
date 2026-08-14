"""
Application Lifespan Handler.

Quản lý vòng đời ứng dụng: khởi tạo resources khi startup,
dọn dẹp khi shutdown. Dùng asynccontextmanager thay cho
@app.on_event("startup"/"shutdown") đã deprecated.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle context manager.

    Startup: Khởi tạo LLM Provider, Database, và các service cần thiết.
    Shutdown: Giải phóng connections, reset cache.
    """
    # ── Startup ──
    logger.info(
        "[START] Starting '%s' [env=%s]...", settings.PROJECT_NAME, settings.ENVIRONMENT
    )
    await _startup()
    logger.info("[START] Application '%s' started successfully.", settings.PROJECT_NAME)

    yield

    # ── Shutdown ──
    logger.info("[STOP] Shutting down '%s'...", settings.PROJECT_NAME)
    await _shutdown()
    logger.info("[STOP] Application shutdown completed.")


async def _startup() -> None:
    """Khởi tạo tất cả resources cần thiết khi ứng dụng khởi động."""

    # 1. LLM Provider — pre-warm để phát hiện lỗi config sớm
    try:
        import os
        from app.routers.dependencies import get_llm_provider_dep

        provider = get_llm_provider_dep()
        logger.info("[OK] LLM Provider ready: %s", type(provider).__name__)
        logger.info(
            "[LANGSMITH] Tracing enabled=%s | Project='%s' | Endpoint='%s' | KeyConfigured=%s",
            os.getenv("LANGCHAIN_TRACING_V2", "false"),
            os.getenv("LANGCHAIN_PROJECT", "ai-agent-bvbank"),
            os.getenv("LANGCHAIN_ENDPOINT", "default"),
            bool(os.getenv("LANGCHAIN_API_KEY")),
        )
    except Exception as ex:
        logger.error("[FAIL] Failed to initialize LLM Provider: %s", ex, exc_info=True)
        # Không crash app — cho phép health check vẫn hoạt động

    # 2. Database — tạo bảng ORM (RagDocuments, RagDocumentRoles, Conversations, ChatMessages)
    try:
        # Import các ORM models để SQLAlchemy nhận biết schema trước khi create_all()
        import app.modules.document.model  # noqa: F401 — RagDocument, RagDocumentRole
        import app.modules.chat.model       # noqa: F401 — Conversation, ChatMessage
        from app.core.database import init_db

        init_db()
        logger.info("[OK] Database schema initialized successfully.")
    except Exception as ex:
        logger.error("[FAIL] Failed to initialize database: %s", ex, exc_info=True)

    # 3. Tạo bảng Documents (Vector Chunks) bằng DDL thủ công
    # Bảng này dùng kiểu VECTOR(1024) không được SQLAlchemy ORM hỗ trợ native trên SQL Server.
    try:
        from app.core.database import engine

        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM sysobjects WHERE name='Documents' AND xtype='U'"
                )
                if not cursor.fetchone():
                    cursor.execute("""
                        CREATE TABLE Documents (
                            id_int    INT IDENTITY(1,1) CONSTRAINT PK_Documents PRIMARY KEY CLUSTERED,
                            id        VARCHAR(255) NOT NULL CONSTRAINT UQ_Documents_id UNIQUE,
                            document  NVARCHAR(MAX),
                            metadata  NVARCHAR(MAX),
                            embedding VECTOR(1024)
                        );
                    """)
                    logger.info(
                        "[OK] Table 'Documents' (Vector Chunks) created via DDL."
                    )
            raw_conn.commit()
        finally:
            raw_conn.close()
    except Exception as ex:
        logger.error("[FAIL] Failed to create Documents table: %s", ex, exc_info=True)


async def _shutdown() -> None:
    """Giải phóng tất cả resources khi ứng dụng tắt."""

    # 1. Reset LLM Provider cache
    from app.routers.dependencies import _reset_caches

    _reset_caches()

    # 2. Database connections
    try:
        from app.core.database import close_db

        close_db()
    except Exception as ex:
        logger.error(
            "[FAIL] Failed to close database connection: %s", ex, exc_info=True
        )

    logger.info("[DONE] All resources released.")
