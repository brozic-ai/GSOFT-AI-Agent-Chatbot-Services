"""
Pydantic Schemas cho module FAQ Knowledge Base.
Dùng cho validation đầu vào API và định dạng phản hồi.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FaqBase(BaseModel):
    """Schema cơ sở chứa các trường dùng chung."""

    question: str = Field(..., min_length=3, description="Nội dung câu hỏi.")
    answer: str = Field(..., min_length=1, description="Câu trả lời.")
    category: str | None = Field(None, max_length=200, description="Phân loại chủ đề.")
    metadata_json: dict[str, Any] | None = Field(
        None, description="Metadata tùy chọn dưới dạng JSON."
    )


class FaqCreate(FaqBase):
    """Schema khi tạo mới 1 FAQ thủ công qua API."""

    pass


class FaqUpdate(BaseModel):
    """Schema khi cập nhật FAQ (tất cả trường đều optional)."""

    question: str | None = Field(None, min_length=3)
    answer: str | None = Field(None, min_length=1)
    category: str | None = Field(None, max_length=200)
    metadata_json: dict[str, Any] | None = None


class FaqResponse(FaqBase):
    """Schema phản hồi trả về client."""

    id: int
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class FaqListResponse(BaseModel):
    """Schema phản hồi danh sách FAQ có phân trang."""

    items: list[FaqResponse]
    total: int
    page: int
    page_size: int


class UploadExcelResponse(BaseModel):
    """Schema phản hồi sau khi upload file Excel nhập liệu FAQ."""

    total_rows: int = Field(..., description="Tổng số dòng dữ liệu trong file Excel.")
    imported_count: int = Field(..., description="Số câu hỏi được nhập thành công.")
    skipped_count: int = Field(..., description="Số dòng bị bỏ qua vì đã tồn tại.")
    error_count: int = Field(..., description="Số dòng bị lỗi (dữ liệu thiếu/sai định dạng).")
    skipped_questions: list[str] = Field(
        default_factory=list,
        description="Danh sách câu hỏi bị bỏ qua (preview tối đa 20 câu).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Danh sách mô tả lỗi (preview tối đa 10 lỗi).",
    )
