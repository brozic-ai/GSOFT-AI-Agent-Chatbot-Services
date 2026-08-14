from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.middleware import register_middlewares
from app.lifespan import lifespan
from app.routers.router import alias_router, api_v1_router

# Khởi tạo logging hệ thống Python AI Backend
setup_logging()
logger = get_logger(__name__)


# FastAPI App
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Dịch vụ Backend AI Agent xử lý LLM, RAG có Phân Quyền Tài Liệu (RBAC) và Multi-Agent.",
    lifespan=lifespan,
)

# Cấu hình CORS Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Đăng ký custom middleware (Logging → Auth → Exception)
register_middlewares(app)

# 1. Đăng ký Router chính RESTful v1
app.include_router(api_v1_router)

# 2. Đăng ký các Router Aliases (Tương thích C# Gateway & Angular Frontend)
app.include_router(alias_router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint trả về thông tin tổng quan và trang API Docs."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "status": "online",
        "docs_url": "/docs",
        "health_check": f"{settings.API_V1_STR}/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
