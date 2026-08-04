from fastapi import APIRouter
from app.modules.health.api.v1.router import router as health_router

api_router = APIRouter()

# Gom tất cả các router thuộc các module nghiệp vụ vào trạm trung chuyển tổng này
api_router.include_router(health_router, prefix="/health", tags=["Health Check"])

# Trong tương lai khi thêm các module khác:
# api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
# api_router.include_router(document_router, prefix="/document", tags=["Document"])
