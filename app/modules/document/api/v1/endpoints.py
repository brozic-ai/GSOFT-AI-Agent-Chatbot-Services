"""
API Routers cho phân hệ Quản lý Tài liệu (Document Management & RBAC Endpoints).
Dành riêng cho phân hệ Quản lý Tài liệu theo chuẩn Clean Architecture & DDD.
"""

import json
import logging
from email.header import decode_header
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, status

from app.modules.document.api.v1.schemas import (
    CreateDocumentMetadataRequest, UpdateDocumentMetadataRequest,
    UpdateDocumentStatusRequest, AddDocumentsRequest, AddDocumentsResponse,
    SearchRequest, SearchResponse, DocumentResponse
)
from app.modules.document.service import DocumentService
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.routers.dependencies import get_document_service, get_vector_retriever

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    request: CreateDocumentMetadataRequest,
    service: DocumentService = Depends(get_document_service),
):
    """Tạo mới siêu dữ liệu tài liệu RAG & danh sách vai trò phân quyền."""
    try:
        doc_id = service.create_document_metadata(request.model_dump())
        return {"status": "success", "id": doc_id}
    except Exception as ex:
        logger.error("[FAIL] Error creating document metadata: %s", ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.get("/documents", response_model=List[DocumentResponse])
async def get_documents_list(
    service: DocumentService = Depends(get_document_service),
):
    """Lấy danh sách tất cả các tài liệu RAG kèm thông tin phân quyền vai trò."""
    try:
        return service.get_documents_list()
    except Exception as ex:
        logger.error("[FAIL] Error listing documents: %s", ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.get("/documents/{id}")
async def get_document(
    id: int,
    service: DocumentService = Depends(get_document_service),
):
    """Lấy thông tin chi tiết của 1 tài liệu RAG."""
    doc = service.get_document_by_id(id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


@router.get("/documents/{id}/roles")
async def get_document_roles(
    id: int,
    service: DocumentService = Depends(get_document_service),
):
    """Lấy danh sách các vai trò (Roles) được cấp quyền xem tài liệu Restricted."""
    return service.get_document_roles(id)


@router.put("/documents/{id}/status")
async def update_document_status(
    id: int,
    request: UpdateDocumentStatusRequest,
    service: DocumentService = Depends(get_document_service),
):
    """Cập nhật trạng thái Ingest của tài liệu từ C# Gateway."""
    try:
        service.update_document_status(id, request.status, request.chunk_count, request.error)
        return {"status": "success"}
    except Exception as ex:
        logger.error("[FAIL] Error updating document status ID=%d: %s", id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.put("/documents/{id}")
async def update_document_metadata(
    id: int,
    request: UpdateDocumentMetadataRequest,
    service: DocumentService = Depends(get_document_service),
):
    """Cập nhật thông tin tài liệu và danh sách vai trò phân quyền mới."""
    try:
        service.update_document_metadata(
            doc_id=id,
            document_name=request.document_name,
            category=request.category,
            access_scope=request.access_scope,
            allowed_roles=request.allowed_roles,
        )
        return {"status": "success"}
    except Exception as ex:
        logger.error("[FAIL] Error updating document metadata ID=%d: %s", id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.delete("/documents/{backend_id}")
async def delete_document(
    backend_id: int,
    service: DocumentService = Depends(get_document_service),
):
    """Xóa tài liệu và toàn bộ các vector chunk liên quan."""
    try:
        file_path = service.delete_document(backend_id)
        return {
            "status": "success",
            "message": f"Successfully deleted document and vector chunks for ID {backend_id}.",
            "filePath": file_path,
        }
    except Exception as ex:
        logger.error("[FAIL] Error deleting document ID=%d: %s", backend_id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    service: DocumentService = Depends(get_document_service),
):
    """Tải lên file và thực hiện Ingestion kèm siêu dữ liệu phân quyền RBAC."""
    if not metadata:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Metadata form field is required.")

    filename = file.filename
    try:
        decoded_parts = decode_header(filename)
        decoded_filename = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_filename += part.decode(encoding or 'utf-8', errors='replace')
            else:
                decoded_filename += part
        if decoded_filename:
            filename = decoded_filename
    except Exception:
        pass

    try:
        custom_metadata = json.loads(metadata)
    except Exception as ex:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid metadata JSON: {ex}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        success, chunk_count = await service.ingest_uploaded_file(
            content=content,
            file_name=filename,
            custom_metadata=custom_metadata,
        )
        return {
            "status": "success",
            "message": f"Successfully ingested {filename}.",
            "chunkCount": chunk_count,
        }
    except Exception as ex:
        logger.error("[FAIL] Error processing document upload: %s", ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    retriever: VectorRetriever = Depends(get_vector_retriever),
):
    """Tìm kiếm Vector Cosine kết hợp lọc phân quyền người dùng (RBAC User Roles)."""
    try:
        roles = request.user_roles or x_user_roles

        response = await retriever.retrieve_context(
            query=request.query,
            top_k=request.top_k,
            content_kind=request.content_kind,
            user_roles=roles,
        )
        return SearchResponse(**response)
    except Exception as ex:
        logger.error("[FAIL] Error searching documents with RBAC: %s", ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))
