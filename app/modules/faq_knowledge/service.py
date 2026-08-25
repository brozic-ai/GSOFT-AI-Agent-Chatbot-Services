"""
FAQ Knowledge Base Service: Business logic cho module FAQ.
Bao gồm xử lý nhập liệu từ file Excel với cơ chế chống trùng lặp.
"""

import io
import json
import logging
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.faq_knowledge.model import FaqKnowledge
from app.modules.faq_knowledge.repository import FaqRepository
from app.modules.faq_knowledge.schema import (
    FaqCreate,
    FaqListResponse,
    FaqResponse,
    FaqUpdate,
    UploadExcelResponse,
)

logger = logging.getLogger(__name__)

# Tên các cột hợp lệ trong file Excel (chấp nhận nhiều cách viết)
_VALID_QUESTION_COLS = {"câu hỏi", "question", "q", "cau hoi"}
_VALID_ANSWER_COLS = {"câu trả lời", "answer", "a", "tra loi", "cau tra loi"}


def _find_column(columns: list[str], valid_names: set[str]) -> str | None:
    """Tìm tên cột thực tế trong DataFrame dựa trên danh sách tên hợp lệ (case-insensitive)."""
    for col in columns:
        if col.strip().lower() in valid_names:
            return col
    return None


class FaqService:
    """Service xử lý các nghiệp vụ liên quan đến FAQ Knowledge Base."""

    def __init__(self, db: Session) -> None:
        self.repo = FaqRepository(db)
        self.db = db

    # -------------------------------------------------------------------------
    # CRUD Thủ công
    # -------------------------------------------------------------------------
    def create_faq(self, payload: FaqCreate) -> FaqResponse:
        """Tạo mới 1 FAQ thủ công. Trả về lỗi 409 nếu câu hỏi đã tồn tại."""
        if self.repo.exists_normalized(payload.question):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Câu hỏi đã tồn tại: '{payload.question[:80]}...'",
            )
        try:
            metadata_str = (
                json.dumps(payload.metadata_json, ensure_ascii=False)
                if payload.metadata_json
                else None
            )
            faq = self.repo.create(
                question=payload.question,
                answer=payload.answer,
                category=payload.category,
                metadata_json=metadata_str,
            )
            self.db.commit()
            self.db.refresh(faq)
            return FaqResponse.model_validate(faq)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Câu hỏi đã tồn tại (unique constraint violation).",
            )

    def get_faq(self, faq_id: int) -> FaqResponse:
        """Lấy 1 FAQ theo ID. Trả về 404 nếu không tìm thấy."""
        faq = self.repo.get_by_id(faq_id)
        if not faq:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy FAQ có ID = {faq_id}.",
            )
        return FaqResponse.model_validate(faq)

    def list_faqs(
        self, page: int = 1, page_size: int = 20, category: str | None = None
    ) -> FaqListResponse:
        """Lấy danh sách FAQ có phân trang."""
        items, total = self.repo.get_all(page=page, page_size=page_size, category=category)
        return FaqListResponse(
            items=[FaqResponse.model_validate(f) for f in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def update_faq(self, faq_id: int, payload: FaqUpdate) -> FaqResponse:
        """Cập nhật FAQ. Trả về 404 nếu không tìm thấy, 409 nếu câu hỏi mới bị trùng."""
        faq = self.repo.get_by_id(faq_id)
        if not faq:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy FAQ có ID = {faq_id}.",
            )

        # Kiểm tra trùng câu hỏi mới (trừ bản ghi đang sửa)
        if payload.question and payload.question != faq.question:
            existing = self.repo.get_by_normalized_question(payload.question)
            if existing and existing.id != faq_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Câu hỏi mới đã tồn tại: '{payload.question[:80]}'.",
                )

        try:
            metadata_str = (
                json.dumps(payload.metadata_json, ensure_ascii=False)
                if payload.metadata_json is not None
                else None
            )
            updated = self.repo.update(
                faq,
                question=payload.question,
                answer=payload.answer,
                category=payload.category,
                metadata_json=metadata_str,
            )
            self.db.commit()
            self.db.refresh(updated)
            return FaqResponse.model_validate(updated)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Câu hỏi đã tồn tại (unique constraint violation).",
            )

    def delete_faq(self, faq_id: int) -> dict[str, str]:
        """Xóa FAQ. Trả về 404 nếu không tìm thấy."""
        faq = self.repo.get_by_id(faq_id)
        if not faq:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy FAQ có ID = {faq_id}.",
            )
        self.repo.delete(faq)
        self.db.commit()
        return {"message": f"Đã xóa FAQ có ID = {faq_id} thành công."}

    # -------------------------------------------------------------------------
    # Nhập liệu từ Excel
    # -------------------------------------------------------------------------
    async def import_from_excel(self, file: UploadFile) -> UploadExcelResponse:
        """
        Đọc file Excel, trích xuất cột Câu hỏi & Câu trả lời, kiểm tra trùng lặp
        và nhập dữ liệu hàng loạt vào bảng FAQ_Knowledge_Base.

        Quy trình:
            1. Đọc nội dung file với pandas.
            2. Dò tìm tên cột Câu hỏi và Câu trả lời (linh hoạt nhiều cách đặt tên).
            3. Lặp từng dòng:
                - Bỏ qua nếu question hoặc answer trống.
                - Bỏ qua (skip) nếu câu hỏi đã tồn tại.
                - Ghi log chi tiết cho từng trường hợp.
            4. Commit toàn bộ batch, trả về thống kê.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Thư viện 'pandas' chưa được cài đặt. Vui lòng liên hệ Admin.",
            ) from exc

        # Kiểm tra định dạng file
        if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chỉ chấp nhận file định dạng .xlsx hoặc .xls.",
            )

        content = await file.read()
        try:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        except Exception as exc:
            logger.error("[FAQ IMPORT] Lỗi đọc file Excel: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Không thể đọc file Excel: {exc}",
            ) from exc

        # Loại bỏ dòng và cột hoàn toàn trống
        df.dropna(how="all", inplace=True)
        columns = list(df.columns)

        # Dò tìm tên cột câu hỏi và câu trả lời
        question_col = _find_column(columns, _VALID_QUESTION_COLS)
        answer_col = _find_column(columns, _VALID_ANSWER_COLS)

        if not question_col or not answer_col:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File Excel phải có cột 'Câu hỏi' và 'Câu trả lời'. "
                    f"Các cột tìm thấy: {columns}. "
                    "Cột hợp lệ: ['Câu hỏi', 'Question', 'Câu trả lời', 'Answer']."
                ),
            )

        total_rows = len(df)
        imported_count = 0
        skipped_count = 0
        error_count = 0
        skipped_questions: list[str] = []
        errors: list[str] = []

        logger.info(
            "[FAQ IMPORT] Bắt đầu import %d dòng từ file '%s'.",
            total_rows,
            file.filename,
        )

        faqs_to_add: list[FaqKnowledge] = []

        for row_idx, row in df.iterrows():
            row_num = int(row_idx) + 2  # +2: header + 1-indexed

            question_raw = str(row.get(question_col, "") or "").strip()
            answer_raw = str(row.get(answer_col, "") or "").strip()

            # Bỏ qua dòng thiếu dữ liệu bắt buộc
            if not question_raw or question_raw.lower() == "nan":
                err_msg = f"Dòng {row_num}: Cột 'Câu hỏi' trống, bỏ qua."
                logger.warning("[FAQ IMPORT] %s", err_msg)
                errors.append(err_msg)
                error_count += 1
                continue
            if not answer_raw or answer_raw.lower() == "nan":
                err_msg = f"Dòng {row_num}: Cột 'Câu trả lời' trống, bỏ qua."
                logger.warning("[FAQ IMPORT] %s", err_msg)
                errors.append(err_msg)
                error_count += 1
                continue

            # Kiểm tra trùng lặp trong DB
            if self.repo.exists_normalized(question_raw):
                logger.info(
                    "[FAQ IMPORT] SKIP Dòng %d (trùng): '%s'",
                    row_num,
                    question_raw[:60],
                )
                if len(skipped_questions) < 20:
                    skipped_questions.append(question_raw[:120])
                skipped_count += 1
                continue

            # Lấy các cột optional nếu có
            category = str(row.get("Category") or row.get("Danh mục") or "").strip() or None
            metadata_str = None

            faq = FaqKnowledge(
                question=question_raw,
                question_normalized=" ".join(question_raw.lower().split()),
                answer=answer_raw,
                category=category,
                metadata_json=metadata_str,
            )
            faqs_to_add.append(faq)
            imported_count += 1

        # Bulk insert
        if faqs_to_add:
            try:
                self.db.add_all(faqs_to_add)
                self.db.commit()
                logger.info(
                    "[FAQ IMPORT] Hoàn thành: import=%d, skip=%d, error=%d.",
                    imported_count,
                    skipped_count,
                    error_count,
                )
            except IntegrityError as exc:
                self.db.rollback()
                logger.error("[FAQ IMPORT] Lỗi bulk insert (IntegrityError): %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Lỗi trùng lặp dữ liệu trong quá trình import. Vui lòng kiểm tra lại file.",
                ) from exc

        return UploadExcelResponse(
            total_rows=total_rows,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=error_count,
            skipped_questions=skipped_questions,
            errors=errors[:10],  # Trả về tối đa 10 lỗi để tránh response quá lớn
        )
