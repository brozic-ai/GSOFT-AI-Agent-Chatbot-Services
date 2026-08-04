import os
from fastapi import APIRouter, status
from app.modules.health.api.v1.schemas import HealthCheckResponse

router = APIRouter()

@router.get("", response_model=HealthCheckResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """Endpoint kiểm tra trạng thái hoạt động của hệ thống (Health Check)."""
    return HealthCheckResponse(
        status="ok",
        environment=os.getenv("ENVIRONMENT", "local"),
        project_name=os.getenv("PROJECT_NAME", "Chatbot BVBank"),
    )
