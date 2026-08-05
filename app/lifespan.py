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
    logger.info("[START] Starting '%s' [env=%s]...", settings.PROJECT_NAME, settings.ENVIRONMENT)
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
        from app.routers.dependencies import get_llm_provider_dep

        provider = get_llm_provider_dep()
        logger.info("[OK] LLM Provider ready: %s", type(provider).__name__)
    except Exception as ex:
        logger.error("[FAIL] Failed to initialize LLM Provider: %s", ex, exc_info=True)
        # Không crash app — cho phép health check vẫn hoạt động

    # 2. Database
    try:
        from app.core.database import init_db
        init_db()
        logger.info("[OK] Database schema initialized successfully.")
    except Exception as ex:
        logger.error("[FAIL] Failed to initialize database: %s", ex, exc_info=True)


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
        logger.error("[FAIL] Failed to close database connection: %s", ex, exc_info=True)

    logger.info("[DONE] All resources released.")
