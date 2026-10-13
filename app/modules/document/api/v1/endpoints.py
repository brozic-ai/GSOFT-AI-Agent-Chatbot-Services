"""
API Routers cho phân hệ Quản lý Tài liệu (Document Management & RBAC Endpoints).
Dành riêng cho phân hệ Quản lý Tài liệu theo chuẩn Clean Architecture & DDD.
"""

import hashlib
import json
import logging
import os
import tempfile
from email.header import decode_header
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.ai.rag.ingestion.pipeline import IngestionPipeline
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.core.user_context import _safe_unquote
from app.modules.document.api.v1.schemas import (
    CreateDocumentMetadataRequest,
    DocumentResponse,
    DuplicateCheckRequest,
    FingerprintRequest,
    SearchRequest,
    SearchResponse,
    UpdateDocumentMetadataRequest,
    UpdateDocumentStatusRequest,
    UploadAcceptedResponse,
    UploadStatusResponse,
)
from app.modules.document.fingerprints import (
    DocumentConflict,
    can_read,
    parse_scope,
    tenant_scope,
)
from app.modules.document.service import DocumentService
from app.routers.dependencies import (
    get_document_service,
    get_vector_retriever,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _scope(caller: Request):
    value = caller.headers.get("X-Tenant-Scope", "host")
    try:
        parse_scope(value)
    except ValueError:
        raise HTTPException(400, detail="Invalid tenant scope") from None
    return value


def _document(caller, service, doc_id, require_access=True):
    doc = service.get_document_by_id(doc_id)
    if not doc or tenant_scope(doc.get("tenant_id")) != _scope(caller):
        raise HTTPException(404, detail="Document not found")
    if require_access and not can_read(
        doc, caller.headers.get("X-User-Roles"), caller.headers.get("X-User-Department")
    ):
        raise HTTPException(404, detail="Document not found")
    return doc


def _conflict_response(ex, caller, service):
    logger.info(
        "RAG event=import_conflict tenant=%s document=%s code=%s trace=%s",
        _scope(caller),
        ex.document_id,
        ex.code,
        caller.headers.get("X-Request-Id", "unknown"),
    )
    payload = {
        "status": "failed",
        "code": ex.code,
        "message": "Tài liệu đã tồn tại hoặc không thể thực hiện thao tác.",
    }
    if ex.document_id:
        doc = service.get_document_by_id(ex.document_id)
        if (
            doc
            and tenant_scope(doc.get("tenant_id")) == _scope(caller)
            and can_read(
                doc,
                caller.headers.get("X-User-Roles"),
                caller.headers.get("X-User-Department"),
            )
        ):
            payload.update(
                documentId=ex.document_id,
                ingestStatus=doc["ingest_status"],
                documentName=doc["document_name"],
            )
        else:
            payload["code"] = "DUPLICATE"
    return JSONResponse(status_code=409, content=payload)


def _stored_source(doc):
    # Only paths already registered by the trusted script, never a browser path.
    path = doc.get("file_path") or ""
    if not os.path.isabs(path) or not os.path.isfile(path):
        raise HTTPException(
            404,
            detail={
                "code": "SOURCE_MISSING",
                "message": "Cần quản trị viên phục hồi file nguồn.",
            },
        )
    return path


def _registered_ingestion_metadata(doc, attempt, caller):
    return {
        "backend_document_id": doc["id"],
        "attemptId": attempt,
        "accessScope": doc["access_scope"],
        "allowedRoles": doc["allowed_roles"],
        "ownerDepartment": doc["owner_department"],
        "category": doc["category"],
        "tenantScope": _scope(caller),
        "traceId": caller.headers.get("X-Request-Id", "unknown"),
    }


@router.get("/{id:int}/source-fingerprint")
async def source_fingerprint(
    id: int, caller: Request, service: DocumentService = Depends(get_document_service)
):
    doc = _document(caller, service, id, require_access=False)
    try:
        with open(_stored_source(doc), "rb") as source:
            return {"sha256": hashlib.file_digest(source, "sha256").hexdigest()}
    except OSError:
        raise HTTPException(
            422,
            detail={
                "code": "UNREADABLE_SOURCE",
                "message": "Không đọc được file nguồn trên host Python.",
            },
        ) from None


@router.post("/{id:int}/retry-stored-source")
async def retry_stored_source(
    id: int,
    caller: Request,
    background_tasks: BackgroundTasks,
    service: DocumentService = Depends(get_document_service),
):
    doc = _document(caller, service, id)
    if doc["ingest_status"] != "Failed":
        return _conflict_response(
            DocumentConflict("RETRY_NOT_ALLOWED", id), caller, service
        )
    path = _stored_source(doc)
    ext = os.path.splitext(doc["file_name"])[1].lower()
    if ext not in {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt"}:
        raise HTTPException(400, detail={"code": "INVALID_EXTENSION"})
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    try:
        digest = hashlib.sha256()
        length = 0
        with os.fdopen(fd, "wb") as target, open(path, "rb") as source:
            while chunk := source.read(1024 * 1024):
                length += len(chunk)
                if length > 50 * 1024 * 1024:
                    raise HTTPException(413, detail={"code": "INVALID_SIZE"})
                digest.update(chunk)
                target.write(chunk)
        if not length or digest.hexdigest() != doc["file_sha256"]:
            raise HTTPException(
                409,
                detail={
                    "code": "SOURCE_CHANGED",
                    "message": "File nguồn không khớp SHA-256 đã lưu.",
                },
            )
        pipeline = IngestionPipeline(
            repository=service.repository, embedding_service=service.embedding_service
        )
        attempt = service.repository.begin_retry(id, _scope(caller), digest.hexdigest())
        task_id, admitted = service.repository.accept_ingestion(
            id, attempt, digest.hexdigest(), _scope(caller), doc["file_name"]
        )
        if admitted:
            background_tasks.add_task(
                pipeline.run_sync,
                task_id=task_id,
                temp_path=temp_path,
                file_name=doc["file_name"],
                file_size=length,
                metadata=_registered_ingestion_metadata(doc, attempt, caller),
            )
            temp_path = None  # Pipeline owns cleanup after admission.
        logger.info(
            "RAG event=retry_accepted tenant=%s document=%s attempt=%s trace=%s",
            _scope(caller),
            id,
            attempt,
            caller.headers.get("X-Request-Id", "unknown"),
        )
        return {
            "status": "success",
            "documentId": id,
            "attemptId": attempt,
            "ingestStatus": "Processing",
        }
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)
    except OSError:
        raise HTTPException(
            422,
            detail={
                "code": "UNREADABLE_SOURCE",
                "message": "Không đọc được file nguồn trên host Python.",
            },
        ) from None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/duplicate-check")
async def duplicate_check(
    request: DuplicateCheckRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    return {
        "results": service.repository.check_fingerprints(
            request.files,
            _scope(caller),
            caller.headers.get("X-User-Roles"),
            caller.headers.get("X-User-Department"),
        )
    }


@router.get("/fingerprints/candidates")
async def fingerprint_candidates(
    caller: Request,
    cursor: int = Query(0, ge=0),
    service: DocumentService = Depends(get_document_service),
):
    return {
        "documents": service.repository.fingerprint_candidates(_scope(caller), cursor),
        "coverage": service.repository.fingerprint_coverage(_scope(caller)),
    }


@router.put("/{id:int}/fingerprint")
async def backfill_fingerprint(
    id: int,
    request: FingerprintRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    _document(caller, service, id, require_access=False)
    try:
        return service.repository.backfill_fingerprint(
            id, request.sha256, _scope(caller)
        )
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)


@router.post("/{id:int}/retry-attempt")
async def retry_attempt(
    id: int,
    request: FingerprintRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    _document(caller, service, id)
    try:
        attempt = service.repository.begin_retry(id, _scope(caller), request.sha256)
        logger.info(
            "RAG event=retry_accepted tenant=%s document=%s attempt=%s trace=%s",
            _scope(caller),
            id,
            attempt,
            caller.headers.get("X-Request-Id", "unknown"),
        )
        return {"documentId": id, "attemptId": attempt, "ingestStatus": "Pending"}
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)


@router.get("/{id:int}/attempts/{attempt_id}")
async def get_attempt(
    id: int,
    attempt_id: str,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    _document(caller, service, id, require_access=False)
    task = service.repository.get_attempt_task(id, attempt_id)
    if not task:
        raise HTTPException(404, detail="Attempt not yet received")
    return task


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_document(
    request: CreateDocumentMetadataRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Tạo mới siêu dữ liệu tài liệu RAG & danh sách vai trò phân quyền."""
    from app.core.config import settings

    if getattr(settings, "RAG_REQUIRE_FILE_SHA256", True) and not request.file_sha256:
        raise HTTPException(400, detail="file_sha256 is required for new imports")
    request.tenant_id = parse_scope(_scope(caller))
    try:
        doc_id = service.create_document_metadata(request.model_dump())
        doc = service.get_document_by_id(doc_id)
        return {
            "status": "success",
            "id": doc_id,
            "attemptId": doc["current_ingestion_attempt_id"],
        }
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)
    except Exception as ex:
        logger.error("[FAIL] Error creating document metadata: %s", ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.get("", response_model=list[DocumentResponse])
@router.get("/", response_model=list[DocumentResponse], include_in_schema=False)
async def get_documents_list(
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Lấy danh sách tất cả các tài liệu RAG kèm thông tin phân quyền vai trò."""
    scope = _scope(caller)
    try:
        return [
            d
            for d in service.get_documents_list()
            if tenant_scope(d.get("tenant_id")) == scope
            and can_read(
                d,
                caller.headers.get("X-User-Roles"),
                caller.headers.get("X-User-Department"),
            )
        ]
    except Exception as ex:
        logger.error("[FAIL] Error listing documents: %s", ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.get("/{id:int}")
async def get_document(
    id: int,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Lấy thông tin chi tiết của 1 tài liệu RAG."""
    return _document(caller, service, id)


@router.get("/{id:int}/roles")
async def get_document_roles(
    id: int,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Lấy danh sách các vai trò (Roles) được cấp quyền xem tài liệu Restricted."""
    _document(caller, service, id)
    return service.get_document_roles(id)


@router.get("/{id:int}/ingestion-status")
async def document_ingestion_status(
    id: int, caller: Request, service: DocumentService = Depends(get_document_service)
):
    # An uploader may choose roles they do not belong to. They still need to
    # follow their own ingestion, without gaining read access to the document.
    doc = _document(caller, service, id, require_access=False)
    visible = can_read(
        doc, caller.headers.get("X-User-Roles"), caller.headers.get("X-User-Department")
    )
    owns_upload = bool(caller.headers.get("X-User-Id")) and doc.get(
        "uploaded_by"
    ) == caller.headers.get("X-User-Id")
    if not visible and not owns_upload:
        raise HTTPException(404, detail="Document not found")
    return {
        "ingest_status": doc["ingest_status"],
        "progress_percent": doc["progress_percent"],
        "canRetry": visible and doc["ingest_status"] == "Failed",
        "ingest_error": doc["ingest_error"]
        if visible
        else ("Xử lý tài liệu thất bại." if doc["ingest_error"] else None),
    }


@router.put("/{id:int}/status")
async def update_document_status(
    id: int,
    request: UpdateDocumentStatusRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Cập nhật trạng thái Ingest của tài liệu từ C# Gateway."""
    _document(caller, service, id, require_access=False)
    try:
        service.update_document_status(
            id, request.status, request.chunk_count, request.error, request.attempt_id
        )
        return {"status": "success"}
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)
    except Exception as ex:
        logger.error(
            "[FAIL] Error updating document status ID=%d: %s", id, ex, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.put("/{id:int}")
@router.post("/{id:int}")
async def update_document_metadata(
    id: int,
    request: UpdateDocumentMetadataRequest,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Cập nhật thông tin tài liệu và danh sách vai trò phân quyền mới."""
    _document(caller, service, id)
    try:
        service.update_document_metadata(
            doc_id=id,
            document_name=request.document_name,
            category=request.category,
            owner_department=request.owner_department,
            description=request.description,
            tags=request.tags,
            access_scope=request.access_scope,
            effective_date=request.effective_date,
            expiration_date=request.expiration_date,
            allowed_roles=request.allowed_roles,
        )
        return {"status": "success"}
    except Exception as ex:
        logger.error(
            "[FAIL] Error updating document metadata ID=%d: %s", id, ex, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.delete("/{backend_id:int}")
async def delete_document(
    backend_id: int,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """Xóa tài liệu và toàn bộ các vector chunk liên quan."""
    _document(caller, service, backend_id)
    try:
        file_path = service.delete_document(backend_id)
        return {
            "status": "success",
            "message": f"Successfully deleted document and vector chunks for ID {backend_id}.",
            "filePath": file_path,
        }
    except DocumentConflict as ex:
        return _conflict_response(ex, caller, service)
    except Exception as ex:
        logger.error(
            "[FAIL] Error deleting document ID=%d: %s", backend_id, ex, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def upload_document(
    caller: Request,
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata form field is required.",
        )

    filename = file.filename
    try:
        decoded_parts = decode_header(filename)
        decoded_filename = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_filename += part.decode(encoding or "utf-8", errors="replace")
            else:
                decoded_filename += part
        if decoded_filename:
            filename = decoded_filename
    except Exception:
        pass

    try:
        custom_metadata = json.loads(metadata)
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metadata JSON: {ex}",
        )

    # 1. Tạo file tạm có extension gốc để MarkItDown và Extractor detect đúng định dạng
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt"}:
        raise HTTPException(400, detail="Unsupported extension")
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    length = 0
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as temp_file:
            while chunk := await file.read(1024 * 1024):
                length += len(chunk)
                if length > 50 * 1024 * 1024:
                    raise HTTPException(413, detail="File exceeds 50 MB")
                digest.update(chunk)
                temp_file.write(chunk)
        if not length:
            raise HTTPException(400, detail="Uploaded file is empty.")
    except HTTPException:
        os.remove(temp_path)
        raise
    except Exception as temp_ex:
        os.remove(temp_path)
        logger.error(
            "[FAIL] Error saving temporary upload file: %s", temp_ex, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save upload temp file.",
        )

    backend_id_val = (
        custom_metadata.get("backend_document_id")
        or custom_metadata.get("backendId")
        or custom_metadata.get("backend_id")
    )
    attempt_id = custom_metadata.get("attemptId") or custom_metadata.get("attempt_id")
    try:
        if not backend_id_val or not str(backend_id_val).isdigit() or not attempt_id:
            raise HTTPException(
                400, detail="documentId and attemptId registration required"
            )
        backend_doc_id = int(backend_id_val)
        task_id, admitted = service.repository.accept_ingestion(
            backend_doc_id, attempt_id, digest.hexdigest(), _scope(caller), filename
        )
        if not admitted:
            os.remove(temp_path)
            return UploadAcceptedResponse(
                task_id=task_id, status=service.get_ingestion_task(task_id)["status"]
            )
        # The registered metadata, not the upload body, controls chunk permissions.
        doc = service.get_document_by_id(backend_doc_id)
        custom_metadata.update(
            backend_document_id=backend_doc_id,
            attemptId=attempt_id,
            accessScope=doc["access_scope"],
            allowedRoles=doc["allowed_roles"],
            ownerDepartment=doc["owner_department"],
            category=doc["category"],
            tenantScope=_scope(caller),
            traceId=caller.headers.get("X-Request-Id", "unknown"),
        )
    except DocumentConflict as ex:
        os.remove(temp_path)
        return _conflict_response(ex, caller, service)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

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
        file_size=length,
        metadata=custom_metadata,
    )

    logger.info(
        "[UPLOAD] Queued async ingestion task_id='%s' for file='%s'", task_id, filename
    )
    return UploadAcceptedResponse(task_id=task_id, status="PENDING")


@router.get("/upload-status/{task_id}", response_model=UploadStatusResponse)
async def get_upload_status(
    task_id: str,
    caller: Request,
    service: DocumentService = Depends(get_document_service),
):
    """
    Cung cấp endpoint cho Frontend / Gateway poll trạng thái và % tiến độ xử lý file theo task_id UUID.
    """
    task_info = service.get_ingestion_task(task_id)
    if not task_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion task with task_id='{task_id}' not found.",
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
        roles = request.user_roles or (
            _safe_unquote(x_user_roles) if x_user_roles else None
        )
        department = request.user_department or (
            _safe_unquote(x_user_department) if x_user_department else None
        )

        response = await retriever.retrieve_context(
            query=request.query,
            top_k=request.top_k,
            content_kind=request.content_kind,
            user_roles=roles,
            user_department=department,
        )
        return SearchResponse(**response)
    except Exception as ex:
        logger.error(
            "[FAIL] Error searching documents with RBAC: %s", ex, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex)
        )


@router.post("/reindex")
async def reindex_documents_api(
    doc_id: Optional[int] = None,
    file_type: Optional[str] = None,
    clean_binary: bool = False,
    reindex_all: bool = False,
    background_tasks: BackgroundTasks = None,
    service: DocumentService = Depends(get_document_service),
):
    """
    Kích hoạt Re-index tài liệu (chạy ngầm qua BackgroundTasks hoặc trực tiếp)
    theo chuẩn Atomic Slide Aggregation và Token Chunker mới.
    """
    import subprocess
    import sys
    from pathlib import Path

    script_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "scripts"
        / "reindex_documents.py"
    )
    if not script_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Re-index script not found.",
        )

    cmd = [sys.executable, str(script_path)]
    if clean_binary:
        cmd.append("--clean-binary")
    if doc_id:
        cmd.extend(["--id", str(doc_id)])
    elif file_type:
        cmd.extend(["--type", file_type])
    elif reindex_all:
        cmd.append("--all")

    # Chạy subprocess trong BackgroundTasks để không block HTTP request
    def _run_reindex_proc(command: list[str]):
        try:
            logger.info("[REINDEX API] Bắt đầu chạy: %s", " ".join(command))
            subprocess.run(command, check=True)
            logger.info("[REINDEX API] Hoàn tất reindex thành công.")
        except Exception as ex:
            logger.error("[REINDEX API] Lỗi khi chạy reindex script: %s", ex)

    if background_tasks:
        background_tasks.add_task(_run_reindex_proc, cmd)
    else:
        _run_reindex_proc(cmd)

    return {
        "status": "Accepted",
        "message": "Re-index process started in background.",
        "command": " ".join(cmd),
    }
