"""
Service tầng nghiệp vụ quản lý tài liệu (Document Business Service).
Đóng gói logic xử lý file tải lên, tách chunk, tạo vector embeddings và phân quyền vai trò.
"""

import logging
import os
import tempfile
from typing import Any

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentService:
    """Business Service cho quản lý tài liệu RAG."""

    def __init__(
        self, repository: DocumentRepository, embedding_service: TeiEmbeddingService
    ):
        self.repository = repository
        self.embedding_service = embedding_service

    def create_document_metadata(self, request_data: dict[str, Any]) -> int:
        """Tạo mới siêu dữ liệu tài liệu RAG và đăng ký vai trò truy cập."""
        return self.repository.create_rag_document(
            document_name=request_data["document_name"],
            file_name=request_data["file_name"],
            file_path=request_data["file_path"],
            file_size=request_data["file_size"],
            category=request_data.get("category"),
            owner_department=request_data.get("owner_department"),
            description=request_data.get("description"),
            tags=request_data.get("tags"),
            access_scope=request_data.get("access_scope", "Public"),
            effective_date=request_data.get("effective_date"),
            expiration_date=request_data.get("expiration_date"),
            uploaded_by=request_data.get("uploaded_by"),
            tenant_id=request_data.get("tenant_id"),
            allowed_roles=request_data.get("allowed_roles", []),
        )

    def get_documents_list(self) -> list[dict[str, Any]]:
        """Lấy danh sách tất cả tài liệu RAG."""
        return self.repository.get_rag_documents_list()

    def get_document_by_id(self, doc_id: int) -> dict[str, Any] | None:
        """Lấy chi tiết 1 tài liệu RAG theo ID."""
        return self.repository.get_rag_document(doc_id)

    def get_document_roles(self, doc_id: int) -> list[str]:
        """Lấy danh sách vai trò được phép truy cập của tài liệu."""
        return self.repository.get_rag_document_roles(doc_id)

    def update_document_status(
        self, doc_id: int, status: str, chunk_count: int, error: str | None = None
    ) -> None:
        """Cập nhật trạng thái Ingest từ Backend Gateway."""
        self.repository.update_rag_document_status(doc_id, status, chunk_count, error)

    def update_document_metadata(
        self,
        doc_id: int,
        document_name: str,
        category: str | None,
        access_scope: str,
        allowed_roles: list[str],
    ) -> None:
        """Cập nhật thông tin tài liệu và danh sách vai trò phân quyền."""
        self.repository.update_rag_document(
            doc_id=doc_id,
            document_name=document_name,
            category=category,
            access_scope=access_scope,
            allowed_roles=allowed_roles,
        )

    def delete_document(self, backend_id: int) -> str | None:
        """Xóa tài liệu và các vector chunk liên quan."""
        return self.repository.delete_rag_document(backend_id)

    def create_ingestion_task(
        self, task_id: str, file_name: str, backend_document_id: int | None = None
    ) -> None:
        """Tạo bản ghi theo dõi tiến độ Ingestion ngầm."""
        self.repository.create_ingestion_task(task_id, file_name, backend_document_id)

    def get_ingestion_task(self, task_id: str) -> dict[str, Any] | None:
        """Lấy thông tin tiến độ IngestionTask theo task_id UUID."""
        return self.repository.get_ingestion_task(task_id)
