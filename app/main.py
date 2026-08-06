from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.middleware import register_middlewares
from app.lifespan import lifespan
from app.routers.router import api_router
from app.modules.document.api.v1.endpoints import router as document_router
from app.modules.chat.api.v1.endpoints import router as chat_router

# Khởi tạo logging (gọi 1 lần duy nhất)
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

# 1. Đăng ký Router tổng RESTful DDD chuẩn tại `/api/v1`
app.include_router(api_router, prefix=settings.API_V1_STR)

# 2. Đăng ký các Alias Router tương thích trực tiếp với C# Backend Gateway (`/db/...` và `/v1/chat/...`)
app.include_router(document_router, prefix="/db", tags=["Legacy C# Gateway DB Endpoints"])
app.include_router(chat_router, prefix="/v1/chat", tags=["Legacy C# Gateway Chat Stream"])


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
