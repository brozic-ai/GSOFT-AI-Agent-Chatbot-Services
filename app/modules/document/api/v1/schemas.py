"""
Pydantic Schemas / DTOs cho phân hệ Quản lý Tài liệu (Document Management & RBAC API).
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class CreateDocumentMetadataRequest(BaseModel):
    """Yêu cầu tạo siêu dữ liệu tài liệu RAG từ C# Gateway."""

    document_name: str
    file_name: str
    file_path: str
    file_size: int
    category: str | None = None
    owner_department: str | None = None
    description: str | None = None
    tags: str | None = None
    access_scope: str = Field(default="Public", description="Public hoặc Restricted")
    effective_date: str | None = None
    expiration_date: str | None = None
    uploaded_by: str | None = None
    tenant_id: int | None = None
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Danh sách Vai trò (Roles) được quyền truy cập",
    )


class UpdateDocumentMetadataRequest(BaseModel):
    """Yêu cầu cập nhật siêu dữ liệu tài liệu & vai trò phân quyền."""

    document_name: str
    category: str | None = None
    access_scope: str = Field(default="Public")
    allowed_roles: list[str] = Field(default_factory=list)


class UpdateDocumentStatusRequest(BaseModel):
    """Yêu cầu cập nhật trạng thái Ingest từ C# Gateway."""

    status: str
    chunk_count: int
    error: str | None = None


class UploadAcceptedResponse(BaseModel):
    """Phản hồi HTTP 202 Accepted khi nhận file upload xử lý ngầm."""
    task_id: str
    status: str = Field(default="PENDING", description="PENDING | PROCESSING | COMPLETED | FAILED")


class UploadStatusResponse(BaseModel):
    """Phản hồi thông tin tiến độ xử lý file khi client poll theo task_id."""
    task_id: str
    file_name: Optional[str] = None
    backend_document_id: Optional[int] = None
    status: str  # PENDING | PROCESSING | COMPLETED | FAILED
    progress_percent: int = 0
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AddDocumentsRequest(BaseModel):

    """Yêu cầu nạp thô danh sách Chunks vào CSDL Vector."""

    documents: list[str]
    ids: list[str]
    metadatas: list[dict[str, Any]] | None = None


class AddDocumentsResponse(BaseModel):
    status: str
    count: int


class SearchRequest(BaseModel):
    """Yêu cầu tìm kiếm Vector kết hợp phân quyền RBAC Vai trò + Phòng ban."""

    query: str
    top_k: int = Field(default=5, alias="top_k")
    content_kind: Optional[str] = Field(default=None, alias="content_kind")
    user_roles: Optional[str] = Field(
        default=None,
        alias="user_roles",
        description="Chuỗi chứa các vai trò của user, phân cách bằng phẩy",
    )
    user_department: Optional[str] = Field(
        default=None,
        alias="user_department",
        description="Tên phòng ban của user",
    )

    model_config = {"populate_by_name": True}


class Citation(BaseModel):
    source: str | None = None
    page: str | None = None
    chunk_id: str
    score: float


class SearchResponse(BaseModel):
    ids: list[list[str]]
    documents: list[list[str]]
    metadatas: list[list[dict[str, Any]]]
    distances: list[list[float]]
    citations: list[list[Citation]]


class DocumentResponse(BaseModel):
    id: int
    document_name: str
    file_name: str
    file_path: str
    file_size: int
    category: Optional[str] = None
    owner_department: Optional[str] = None
    access_scope: str
    ingest_status: str
    chunk_count: int
    creation_time: str | None = None
    allowed_roles: list[str] = Field(default_factory=list)
