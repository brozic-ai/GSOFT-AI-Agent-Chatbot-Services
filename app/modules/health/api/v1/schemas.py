from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    status: str = Field(
        ..., description="Trạng thái hệ thống", json_schema_extra={"example": "ok"}
    )
    environment: str = Field(
        ..., description="Môi trường hoạt động", json_schema_extra={"example": "local"}
    )
    project_name: str = Field(
        ..., description="Tên dự án", json_schema_extra={"example": "Chatbot BVBank"}
    )
