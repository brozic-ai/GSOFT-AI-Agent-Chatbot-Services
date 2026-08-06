"""
API Routers cho phân hệ Quản lý Tài liệu (Document Management & RBAC Endpoints).
Dành riêng cho phân hệ Quản lý Tài liệu theo chuẩn Clean Architecture & DDD.
"""

import json
import logging
import os
import tempfile
import uuid
from email.header import decode_header
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, status, BackgroundTasks

from app.modules.document.api.v1.schemas import (
    CreateDocumentMetadataRequest, UpdateDocumentMetadataRequest,
    UpdateDocumentStatusRequest, AddDocumentsRequest, AddDocumentsResponse,
    SearchRequest, SearchResponse, DocumentResponse,
    UploadAcceptedResponse, UploadStatusResponse
)
from app.modules.document.service import DocumentService
from app.ai.rag.ingestion.pipeline import IngestionPipeline
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.routers.dependencies import get_document_service, get_vector_retriever, get_embedding_service


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


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadAcceptedResponse)
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    background_tasks: BackgroundTasks = None,
    service: DocumentService = Depends(get_document_service),
):
    """
    Tải lên file bất đồng bộ (Async Ingestion with BackgroundTasks).
    Nhanh chóng tạo task_id UUID, lưu file tạm, lưu IngestionTask PENDING và trả về 202 Accepted lập tức.
    """
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

    # 1. Tạo file tạm để pipeline đọc ngầm
    fd, temp_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            temp_file.write(content)
    except Exception as temp_ex:
        logger.error("[FAIL] Error saving temporary upload file: %s", temp_ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save upload temp file.")

    # 2. Khởi tạo task_id UUID
    task_id = str(uuid.uuid4())
    backend_id_val = custom_metadata.get("backend_document_id") or custom_metadata.get("backendId") or custom_metadata.get("backend_id") or custom_metadata.get("id")
    backend_doc_id = int(backend_id_val) if backend_id_val and str(backend_id_val).isdigit() else None

    # 3. Tạo bản ghi PENDING trong DB
    try:
        service.create_ingestion_task(
            task_id=task_id,
            file_name=filename,
            backend_document_id=backend_doc_id,
        )
    except Exception as task_ex:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error("[FAIL] Error creating IngestionTask: %s", task_ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(task_ex))

    # 4. Đưa IngestionPipeline vào BackgroundTasks
    pipeline = IngestionPipeline(
        repository=service.repository,
        embedding_service=service.embedding_service,
    )
    background_tasks.add_task(
        pipeline.run_sync,
        task_id=task_id,
        temp_path=temp_path,
        file_name=filename,
        file_size=len(content),
        metadata=custom_metadata,
    )

    logger.info("[UPLOAD] Queued async ingestion task_id='%s' for file='%s'", task_id, filename)
    return UploadAcceptedResponse(task_id=task_id, status="PENDING")


@router.get("/upload-status/{task_id}", response_model=UploadStatusResponse)
async def get_upload_status(
    task_id: str,
    service: DocumentService = Depends(get_document_service),
):
    """
    Cung cấp endpoint cho Frontend / Gateway poll trạng thái và % tiến độ xử lý file theo task_id UUID.
    """
    task_info = service.get_ingestion_task(task_id)
    if not task_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion task with task_id='{task_id}' not found."
        )
    return UploadStatusResponse(**task_info)



@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    x_user_department: Optional[str] = Header(None, alias="X-User-Department"),
    retriever: VectorRetriever = Depends(get_vector_retriever),
):
    """Tìm kiếm Vector Cosine kết hợp lọc phân quyền người dùng (RBAC User Roles + Department)."""
    try:
        roles = request.user_roles or x_user_roles
        department = request.user_department or x_user_department

        response = await retriever.retrieve_context(
            query=request.query,
            top_k=request.top_k,
            content_kind=request.content_kind,
            user_roles=roles,
            user_department=department,
        )
        return SearchResponse(**response)
    except Exception as ex:
        logger.error("[FAIL] Error searching documents with RBAC: %s", ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))
