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
        from app.llmops.langfuse import is_langfuse_configured
        logger.info(
            "[LANGFUSE] Tracing enabled=%s | Host='%s' | KeyConfigured=%s",
            getattr(settings, "LANGFUSE_ENABLED", False),
            getattr(settings, "LANGFUSE_HOST", "http://localhost:3000"),
            is_langfuse_configured(),
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

    # 4. Tạo Full-Text Catalog & Index cho cột `document` của bảng Documents
    # Dùng LANGUAGE 0 (Neutral) — SQL Server không có word-breaker tiếng Việt native;
    # Neutral tách theo khoảng trắng, phù hợp nhất cho văn bản tiếng Việt đã chuẩn hóa.
    try:
        import pyodbc as _pyodbc

        _conn = _pyodbc.connect(settings.SQLSERVER_CONNECTIONSTRING, autocommit=True)
        try:
            with _conn.cursor() as _cur:
                # 4a. Tạo Full-Text Catalog nếu chưa có
                _cur.execute(
                    "IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs "
                    "WHERE name = 'FtCatalog_Documents') "
                    "CREATE FULLTEXT CATALOG FtCatalog_Documents AS DEFAULT;"
                )
                # 4b. Tạo Full-Text Index trên cột document (dùng UQ_Documents_id làm unique key)
                _cur.execute(
                    "IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes "
                    "WHERE object_id = OBJECT_ID('dbo.Documents')) "
                    "CREATE FULLTEXT INDEX ON dbo.Documents(document LANGUAGE 0) "
                    "KEY INDEX UQ_Documents_id ON FtCatalog_Documents "
                    "WITH CHANGE_TRACKING AUTO;"
                )
            logger.info("[OK] Full-Text Catalog and Index on 'Documents.document' are ready.")
        finally:
            _conn.close()
    except Exception as ex:
        logger.warning(
            "[WARN] Full-Text Search setup skipped (FTS may not be supported on this SQL Server edition): %s",
            ex,
        )


    # 5. Tạo bảng FaqVectors (Vector Store riêng cho FAQ Knowledge Base)
    # Dùng VECTOR(1024) — SQL Server kiểu native, phải tạo thủ công bằng DDL.
    try:
        raw_conn2 = engine.raw_connection()
        try:
            with raw_conn2.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM sysobjects WHERE name='FaqVectors' AND xtype='U'"
                )
                if not cursor.fetchone():
                    cursor.execute("""
                        CREATE TABLE FaqVectors (
                            id_int   INT IDENTITY(1,1) CONSTRAINT PK_FaqVectors PRIMARY KEY CLUSTERED,
                            faq_id   INT NOT NULL CONSTRAINT UQ_FaqVectors_faq_id UNIQUE,
                            question NVARCHAR(MAX),
                            answer   NVARCHAR(MAX),
                            embedding VECTOR(1024)
                        );
                    """)
                    logger.info(
                        "[OK] Table 'FaqVectors' (FAQ Vector Store) created via DDL."
                    )
            raw_conn2.commit()
        finally:
            raw_conn2.close()
    except Exception as ex:
        logger.error("[FAIL] Failed to create FaqVectors table: %s", ex, exc_info=True)

    # 6. Tạo Full-Text Catalog & Index cho bảng FaqVectors (cột question và answer)
    try:
        import pyodbc as _pyodbc2

        _conn2 = _pyodbc2.connect(settings.SQLSERVER_CONNECTIONSTRING, autocommit=True)
        try:
            with _conn2.cursor() as _cur2:
                # 6a. Tạo Full-Text Catalog nếu chưa có
                _cur2.execute(
                    "IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs "
                    "WHERE name = 'FtCatalog_FaqVectors') "
                    "CREATE FULLTEXT CATALOG FtCatalog_FaqVectors AS DEFAULT;"
                )
                # 6b. Tạo Full-Text Index trên cột question và answer
                _cur2.execute(
                    "IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes "
                    "WHERE object_id = OBJECT_ID('dbo.FaqVectors')) "
                    "CREATE FULLTEXT INDEX ON dbo.FaqVectors(question LANGUAGE 0, answer LANGUAGE 0) "
                    "KEY INDEX UQ_FaqVectors_faq_id ON FtCatalog_FaqVectors "
                    "WITH CHANGE_TRACKING AUTO;"
                )
            logger.info("[OK] Full-Text Catalog and Index on 'FaqVectors' are ready.")
        finally:
            _conn2.close()
    except Exception as ex:
        logger.warning(
            "[WARN] FaqVectors Full-Text Search setup skipped: %s", ex
        )


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

    # 3. Flush Langfuse traces
    try:
        from app.llmops.langfuse import flush_langfuse

        flush_langfuse()
    except Exception as ex:
        logger.debug("[LANGFUSE] Flush on shutdown: %s", ex)

    logger.info("[DONE] All resources released.")
