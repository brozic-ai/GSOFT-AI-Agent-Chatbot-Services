from fastapi import APIRouter, status

from app.core.config import settings
from app.modules.health.api.v1.schemas import HealthCheckResponse

router = APIRouter()


@router.get("", response_model=HealthCheckResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """Endpoint kiểm tra trạng thái hoạt động của hệ thống (Health Check)."""
    return HealthCheckResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        project_name=settings.PROJECT_NAME,
    )
