"""
Router tổng trung chuyển cho ứng dụng FastAPI.
Gom tất cả các Sub-routers thuộc các Module nghiệp vụ (Health, Document RBAC, Chat RAG).
"""

from fastapi import APIRouter

from app.modules.health.api.v1.router import router as health_router
from app.modules.document.api.v1.router import router as document_router
from app.modules.chat.api.v1.router import router as chat_router

api_router = APIRouter()

# Register sub-routers theo chuẩn RESTful DDD
api_router.include_router(health_router, prefix="/health", tags=["Health Check"])
api_router.include_router(document_router, prefix="", tags=["Document Management & RBAC"])
api_router.include_router(chat_router, prefix="/chat", tags=["Chat RAG SSE"])
