"""
Pydantic Schemas / DTOs cho phân hệ Quản lý Tài liệu (Document Management & RBAC API).
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CreateDocumentMetadataRequest(BaseModel):
    """Yêu cầu tạo siêu dữ liệu tài liệu RAG từ C# Gateway."""
    document_name: str
    file_name: str
    file_path: str
    file_size: int
    category: Optional[str] = None
    owner_department: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    access_scope: str = Field(default="Public", description="Public hoặc Restricted")
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    uploaded_by: Optional[str] = None
    tenant_id: Optional[int] = None
    allowed_roles: List[str] = Field(default_factory=list, description="Danh sách Vai trò (Roles) được quyền truy cập")


class UpdateDocumentMetadataRequest(BaseModel):
    """Yêu cầu cập nhật siêu dữ liệu tài liệu & vai trò phân quyền."""
    document_name: str
    category: Optional[str] = None
    access_scope: str = Field(default="Public")
    allowed_roles: List[str] = Field(default_factory=list)


class UpdateDocumentStatusRequest(BaseModel):
    """Yêu cầu cập nhật trạng thái Ingest từ C# Gateway."""
    status: str
    chunk_count: int
    error: Optional[str] = None


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
    documents: List[str]
    ids: List[str]
    metadatas: Optional[List[Dict[str, Any]]] = None


class AddDocumentsResponse(BaseModel):
    status: str
    count: int


class SearchRequest(BaseModel):
    """Yêu cầu tìm kiếm Vector kết hợp phân quyền RBAC Vai trò + Phòng ban."""
    query: str
    top_k: int = Field(default=5, alias="top_k")
    content_kind: Optional[str] = Field(default=None, alias="content_kind")
    user_roles: Optional[str] = Field(default=None, alias="user_roles", description="Chuỗi chứa các vai trò của user, phân cách bằng phẩy")
    user_department: Optional[str] = Field(default=None, alias="user_department", description="Tên phòng ban của user")

    model_config = {
        "populate_by_name": True
    }


class Citation(BaseModel):
    source: Optional[str] = None
    page: Optional[str] = None
    chunk_id: str
    score: float


class SearchResponse(BaseModel):
    ids: List[List[str]]
    documents: List[List[str]]
    metadatas: List[List[Dict[str, Any]]]
    distances: List[List[float]]
    citations: List[List[Citation]]


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
    creation_time: Optional[str] = None
    allowed_roles: List[str] = Field(default_factory=list)
