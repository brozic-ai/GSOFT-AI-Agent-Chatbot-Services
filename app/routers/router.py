"""
Router tổng trung chuyển cho ứng dụng FastAPI.
Gom tất cả các Sub-routers thuộc các Module nghiệp vụ (Health, Document RBAC, Chat RAG)
dưới một namespace RESTful duy nhất (/api/v1), dùng chung cho cả C# Gateway & Angular Frontend.
"""

from fastapi import APIRouter

from app.modules.chat.api.v1.endpoints import router as chat_router
from app.modules.document.api.v1.endpoints import router as document_router
from app.modules.faq_knowledge.api.v1.endpoints import router as faq_router
from app.modules.health.api.v1.router import router as health_router

# Router chuẩn RESTful DDD (/api/v1) — nguồn định danh route duy nhất
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router, prefix="/health", tags=["Health Check"])
api_v1_router.include_router(
    document_router, prefix="/documents", tags=["Document Management & RBAC"]
)
api_v1_router.include_router(chat_router, prefix="/chat", tags=["Chat RAG SSE"])
api_v1_router.include_router(faq_router, prefix="/faq", tags=["FAQ Knowledge Base"])
