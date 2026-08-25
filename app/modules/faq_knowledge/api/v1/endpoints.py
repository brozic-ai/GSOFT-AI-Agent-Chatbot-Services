"""
FAQ Knowledge Base API Endpoints.
Cung cấp CRUD thủ công và endpoint upload file Excel để nhập liệu hàng loạt.
Tự động đồng bộ Vector Store (FaqVectors) khi CRUD thông qua TeiEmbeddingService.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.core.database import get_db
from app.modules.faq_knowledge.schema import (
    FaqCreate,
    FaqListResponse,
    FaqResponse,
    FaqUpdate,
    UploadExcelResponse,
)
from app.modules.faq_knowledge.service import FaqService

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_embedding_service() -> TeiEmbeddingService | None:
    """Dependency khởi tạo TeiEmbeddingService để tạo vector embeddings cho FAQ."""
    try:
        return TeiEmbeddingService()
    except Exception as ex:  # noqa: BLE001
        logger.warning(
            "[FAQ] Không thể khởi tạo TeiEmbeddingService: %s. "
            "CRUD FAQ vẫn hoạt động nhưng sẽ không đồng bộ vector.",
            ex,
        )
        return None


def _get_service(
    db: Session = Depends(get_db),
    embedding_service: TeiEmbeddingService | None = Depends(_get_embedding_service),
) -> FaqService:
    """FastAPI Dependency khởi tạo FaqService với DB session và Embedding Service."""
    return FaqService(db=db, embedding_service=embedding_service)


# ---------------------------------------------------------------------------
# READ - Danh sách & Chi tiết
# ---------------------------------------------------------------------------
@router.get(
    "/",
    response_model=FaqListResponse,
    summary="Lấy danh sách FAQ",
    description="Lấy danh sách câu hỏi thường gặp, hỗ trợ phân trang và lọc theo danh mục.",
)
def list_faqs(
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)."),
    page_size: int = Query(20, ge=1, le=100, description="Số bản ghi mỗi trang (tối đa 100)."),
    category: str | None = Query(None, description="Lọc theo danh mục (category)."),
    service: FaqService = Depends(_get_service),
) -> FaqListResponse:
    return service.list_faqs(page=page, page_size=page_size, category=category)


@router.get(
    "/{faq_id}",
    response_model=FaqResponse,
    summary="Lấy chi tiết 1 FAQ",
    description="Lấy thông tin chi tiết của một câu hỏi thường gặp theo ID.",
)
def get_faq(
    faq_id: int,
    service: FaqService = Depends(_get_service),
) -> FaqResponse:
    return service.get_faq(faq_id)


# ---------------------------------------------------------------------------
# CREATE - Thêm thủ công
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=FaqResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm FAQ thủ công",
    description=(
        "Thêm mới một câu hỏi thường gặp. Tự động tạo embedding và đồng bộ sang FaqVectors. "
        "Trả về 409 nếu câu hỏi đã tồn tại."
    ),
)
async def create_faq(
    payload: FaqCreate,
    service: FaqService = Depends(_get_service),
) -> FaqResponse:
    return await service.create_faq(payload)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
@router.put(
    "/{faq_id}",
    response_model=FaqResponse,
    summary="Cập nhật FAQ",
    description=(
        "Cập nhật nội dung câu hỏi hoặc câu trả lời. "
        "Nếu question/answer thay đổi, tự động tạo lại embedding và cập nhật FaqVectors. "
        "Các trường không truyền sẽ giữ nguyên."
    ),
)
async def update_faq(
    faq_id: int,
    payload: FaqUpdate,
    service: FaqService = Depends(_get_service),
) -> FaqResponse:
    return await service.update_faq(faq_id, payload)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
@router.delete(
    "/{faq_id}",
    status_code=status.HTTP_200_OK,
    summary="Xóa FAQ",
    description="Xóa vĩnh viễn một câu hỏi thường gặp khỏi cơ sở dữ liệu và FaqVectors.",
)
def delete_faq(
    faq_id: int,
    service: FaqService = Depends(_get_service),
) -> dict:
    return service.delete_faq(faq_id)


# ---------------------------------------------------------------------------
# UPLOAD EXCEL - Nhập liệu hàng loạt
# ---------------------------------------------------------------------------
@router.post(
    "/upload-excel",
    response_model=UploadExcelResponse,
    status_code=status.HTTP_200_OK,
    summary="Nhập liệu FAQ từ file Excel",
    description=(
        "Upload file Excel (.xlsx/.xls) có 2 cột 'Câu hỏi' và 'Câu trả lời'. "
        "Hệ thống tự động kiểm tra trùng lặp, bỏ qua (skip) câu hỏi đã tồn tại, "
        "batch embed và đồng bộ sang FaqVectors sau khi insert thành công. "
        "Trả về thống kê số dòng import / bỏ qua."
    ),
)
async def upload_excel(
    file: UploadFile = File(..., description="File Excel (.xlsx hoặc .xls) chứa dữ liệu FAQ."),
    service: FaqService = Depends(_get_service),
) -> UploadExcelResponse:
    logger.info("[API] Nhận yêu cầu upload Excel FAQ: '%s'", file.filename)
    return await service.import_from_excel(file)


# ---------------------------------------------------------------------------
# SYNC VECTORS - Đồng bộ hàng loạt
# ---------------------------------------------------------------------------
@router.post(
    "/sync-vectors",
    status_code=status.HTTP_200_OK,
    summary="Đồng bộ Vector Store hàng loạt",
    description=(
        "Quét toàn bộ FAQ chưa có vector trong bảng FaqVectors và tự động tạo embedding. "
        "Hữu ích sau khi import dữ liệu cũ hoặc khi EmbeddingService bị gián đoạn. "
        "Mỗi lần gọi xử lý tối đa `limit` bản ghi (mặc định 500)."
    ),
)
async def sync_faq_vectors(
    limit: int = Query(500, ge=1, le=5000, description="Số FAQ tối đa cần sync trong một lần gọi."),
    service: FaqService = Depends(_get_service),
) -> dict[str, Any]:
    logger.info("[API] Kích hoạt sync-vectors FAQ, limit=%d.", limit)
    return await service.sync_all_vectors(limit=limit)
