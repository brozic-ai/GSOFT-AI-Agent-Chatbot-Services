"""
FAQ Knowledge Base API Endpoints.
Cung cấp CRUD thủ công và endpoint upload file Excel để nhập liệu hàng loạt.
"""

import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

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


def _get_service(db: Session = Depends(get_db)) -> FaqService:
    """FastAPI Dependency khởi tạo FaqService với DB session."""
    return FaqService(db)


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
    description="Thêm mới một câu hỏi thường gặp vào cơ sở dữ liệu. Trả về 409 nếu câu hỏi đã tồn tại.",
)
def create_faq(
    payload: FaqCreate,
    service: FaqService = Depends(_get_service),
) -> FaqResponse:
    return service.create_faq(payload)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
@router.put(
    "/{faq_id}",
    response_model=FaqResponse,
    summary="Cập nhật FAQ",
    description="Cập nhật nội dung câu hỏi hoặc câu trả lời. Các trường không truyền sẽ giữ nguyên.",
)
def update_faq(
    faq_id: int,
    payload: FaqUpdate,
    service: FaqService = Depends(_get_service),
) -> FaqResponse:
    return service.update_faq(faq_id, payload)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
@router.delete(
    "/{faq_id}",
    status_code=status.HTTP_200_OK,
    summary="Xóa FAQ",
    description="Xóa vĩnh viễn một câu hỏi thường gặp khỏi cơ sở dữ liệu.",
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
        "Hệ thống tự động kiểm tra trùng lặp, bỏ qua (skip) câu hỏi đã tồn tại "
        "và trả về thống kê số dòng import thành công / bị bỏ qua."
    ),
)
async def upload_excel(
    file: UploadFile = File(..., description="File Excel (.xlsx hoặc .xls) chứa dữ liệu FAQ."),
    service: FaqService = Depends(_get_service),
) -> UploadExcelResponse:
    logger.info("[API] Nhận yêu cầu upload Excel FAQ: '%s'", file.filename)
    return await service.import_from_excel(file)
