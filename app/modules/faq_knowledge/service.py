"""
FAQ Knowledge Base Service: Business logic cho module FAQ.
Bao gồm xử lý nhập liệu từ file Excel với cơ chế chống trùng lặp.
Đồng bộ Vector Store (bảng dbo.FaqVectors) tự động khi CRUD.
Kế thừa TeiEmbeddingService từ hệ thống RAG để tạo embeddings.
"""

import io
import json
import logging
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.rag.embedding.service import TeiEmbeddingService
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

# Kích thước batch khi vectorize trong quá trình import Excel hoặc sync hàng loạt
_EMBED_BATCH_SIZE = 16


def _find_column(columns: list[str], valid_names: set[str]) -> str | None:
    """Tìm tên cột thực tế trong DataFrame dựa trên danh sách tên hợp lệ (case-insensitive)."""
    for col in columns:
        if col.strip().lower() in valid_names:
            return col
    return None


class FaqService:
    """Service xử lý các nghiệp vụ liên quan đến FAQ Knowledge Base.

    Đồng bộ tự động sang bảng FaqVectors (Vector Store) khi CRUD.
    Nếu embedding_service=None thì CRUD vẫn hoạt động bình thường
    nhưng sẽ ghi cảnh báo và bỏ qua bước vectorize.
    """

    def __init__(self, db: Session, embedding_service: TeiEmbeddingService | None = None) -> None:
        self.repo = FaqRepository(db)
        self.db = db
        self.embedding_service = embedding_service

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    async def _try_upsert_vector(self, faq: FaqKnowledge) -> None:
        """Tạo embedding và upsert vào FaqVectors. Ghi warning nếu lỗi (không crash)."""
        if not self.embedding_service:
            logger.warning(
                "[FAQ VECTOR] EmbeddingService không được cấu hình. Bỏ qua vectorize faq_id=%d.",
                faq.id,
            )
            return
        try:
            embeddings = await self.embedding_service.embed_texts([faq.question])
            if not embeddings or not embeddings[0]:
                logger.warning("[FAQ VECTOR] Embedding rỗng cho faq_id=%d. Bỏ qua.", faq.id)
                return
            self.repo.upsert_faq_vector(
                faq_id=faq.id,
                question=faq.question,
                answer=faq.answer,
                embedding=embeddings[0],
            )
            logger.info("[FAQ VECTOR] Đã upsert vector cho faq_id=%d.", faq.id)
        except Exception as ex:  # noqa: BLE001
            logger.warning(
                "[FAQ VECTOR] Không thể vectorize faq_id=%d: %s. "
                "Dữ liệu vẫn được lưu trong FAQ_Knowledge_Base.",
                faq.id,
                ex,
            )

    def _try_delete_vector(self, faq_id: int) -> None:
        """Xóa vector trong FaqVectors. Ghi warning nếu lỗi (không crash)."""
        try:
            self.repo.delete_faq_vector(faq_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning(
                "[FAQ VECTOR] Không thể xóa vector faq_id=%d: %s.", faq_id, ex
            )

    # -------------------------------------------------------------------------
    # CRUD Thủ công
    # -------------------------------------------------------------------------
    async def create_faq(self, payload: FaqCreate) -> FaqResponse:
        """Tạo mới 1 FAQ thủ công.
        Sau khi lưu vào DB, tự động tạo embedding và upsert vào FaqVectors.
        Trả về 409 nếu câu hỏi đã tồn tại.
        """
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

            # Đồng bộ vector — không-blocking, lỗi sẽ chỉ ghi warning
            await self._try_upsert_vector(faq)

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

    async def update_faq(self, faq_id: int, payload: FaqUpdate) -> FaqResponse:
        """Cập nhật FAQ.
        Nếu question hoặc answer thay đổi → tự động tạo lại embedding và upsert vào FaqVectors.
        Trả về 404 nếu không tìm thấy, 409 nếu câu hỏi mới bị trùng.
        """
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

        # Theo dõi xem question/answer có thay đổi không để quyết định re-embed
        needs_reembed = (
            (payload.question is not None and payload.question != faq.question)
            or (payload.answer is not None and payload.answer != faq.answer)
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

            # Chỉ re-embed nếu nội dung câu hỏi / câu trả lời thực sự thay đổi
            if needs_reembed:
                await self._try_upsert_vector(updated)

            return FaqResponse.model_validate(updated)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Câu hỏi đã tồn tại (unique constraint violation).",
            )

    def delete_faq(self, faq_id: int) -> dict[str, str]:
        """Xóa FAQ và đồng bộ xóa vector trong FaqVectors.
        Trả về 404 nếu không tìm thấy.
        """
        faq = self.repo.get_by_id(faq_id)
        if not faq:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy FAQ có ID = {faq_id}.",
            )
        self.repo.delete(faq)
        self.db.commit()

        # Xóa vector tương ứng trong FaqVectors
        self._try_delete_vector(faq_id)

        return {"message": f"Đã xóa FAQ có ID = {faq_id} thành công."}

    # -------------------------------------------------------------------------
    # Nhập liệu từ Excel
    # -------------------------------------------------------------------------
    async def import_from_excel(self, file: UploadFile) -> UploadExcelResponse:
        """
        Đọc file Excel, trích xuất cột Câu hỏi & Câu trả lời, kiểm tra trùng lặp
        và nhập dữ liệu hàng loạt vào bảng FAQ_Knowledge_Base.
        Sau khi insert thành công, tự động batch embed và upsert vào FaqVectors.

        Quy trình:
            1. Đọc nội dung file với pandas.
            2. Dò tìm tên cột Câu hỏi và Câu trả lời (linh hoạt nhiều cách đặt tên).
            3. Lặp từng dòng:
                - Bỏ qua nếu question hoặc answer trống.
                - Bỏ qua (skip) nếu câu hỏi đã tồn tại.
                - Ghi log chi tiết cho từng trường hợp.
            4. Bulk insert vào FAQ_Knowledge_Base.
            5. Batch embed (EMBED_BATCH_SIZE dòng/lần) và upsert vào FaqVectors.
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

        # Bulk insert vào FAQ_Knowledge_Base
        if faqs_to_add:
            try:
                self.db.add_all(faqs_to_add)
                self.db.commit()

                # Refresh để lấy id được DB tự sinh (IDENTITY)
                for faq in faqs_to_add:
                    self.db.refresh(faq)

                logger.info(
                    "[FAQ IMPORT] Bulk insert hoàn thành: import=%d, skip=%d, error=%d.",
                    imported_count,
                    skipped_count,
                    error_count,
                )

                # Batch embed & upsert vào FaqVectors
                await self._bulk_vectorize(faqs_to_add)

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

    # -------------------------------------------------------------------------
    # Batch Vectorize & Sync
    # -------------------------------------------------------------------------
    async def _bulk_vectorize(self, faqs: list[FaqKnowledge]) -> None:
        """
        Vectorize danh sách FAQ theo từng mini-batch và upsert vào FaqVectors.
        Tương tự cơ chế mini-batching của IngestionPipeline trong RAG.
        """
        if not self.embedding_service:
            logger.warning(
                "[FAQ VECTOR] EmbeddingService không được cấu hình. Bỏ qua batch vectorize."
            )
            return

        total = len(faqs)
        logger.info("[FAQ VECTOR] Bắt đầu batch embed %d câu hỏi...", total)

        for batch_start in range(0, total, _EMBED_BATCH_SIZE):
            batch = faqs[batch_start: batch_start + _EMBED_BATCH_SIZE]
            questions = [f.question for f in batch]
            try:
                embeddings = await self.embedding_service.embed_texts(questions)
                items = [
                    (f.id, f.question, f.answer, embeddings[i])
                    for i, f in enumerate(batch)
                    if embeddings[i]
                ]
                self.repo.bulk_upsert_faq_vectors(items)
                logger.info(
                    "[FAQ VECTOR] Batch %d-%d/%d: upserted %d vectors.",
                    batch_start + 1,
                    min(batch_start + _EMBED_BATCH_SIZE, total),
                    total,
                    len(items),
                )
            except Exception as ex:  # noqa: BLE001
                logger.warning(
                    "[FAQ VECTOR] Lỗi batch embed tại batch %d: %s. Bỏ qua batch này.",
                    batch_start,
                    ex,
                )

    async def sync_all_vectors(self, limit: int = 500) -> dict[str, Any]:
        """
        Quét toàn bộ FAQ chưa có vector trong FaqVectors và tạo embedding hàng loạt.
        Dùng cho endpoint POST /api/v1/faq/sync-vectors sau khi import dữ liệu cũ.

        Args:
            limit: Số FAQ tối đa cần sync trong một lần gọi.

        Returns:
            Dict thống kê: {'synced': int, 'failed': int, 'total_missing': int}.
        """
        faqs = self.repo.get_faqs_without_vector(limit=limit)
        total_missing = len(faqs)

        if not faqs:
            logger.info("[FAQ VECTOR] Tất cả FAQ đã có vector. Không cần sync.")
            return {"synced": 0, "failed": 0, "total_missing": 0}

        if not self.embedding_service:
            logger.warning("[FAQ VECTOR] EmbeddingService không được cấu hình. Không thể sync.")
            return {"synced": 0, "failed": total_missing, "total_missing": total_missing}

        synced = 0
        failed = 0

        for batch_start in range(0, total_missing, _EMBED_BATCH_SIZE):
            batch = faqs[batch_start: batch_start + _EMBED_BATCH_SIZE]
            questions = [f.question for f in batch]
            try:
                embeddings = await self.embedding_service.embed_texts(questions)
                items = [
                    (f.id, f.question, f.answer, embeddings[i])
                    for i, f in enumerate(batch)
                    if embeddings[i]
                ]
                self.repo.bulk_upsert_faq_vectors(items)
                synced += len(items)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[FAQ VECTOR] Sync batch lỗi tại index %d: %s", batch_start, ex)
                failed += len(batch)

        logger.info(
            "[FAQ VECTOR] sync_all_vectors hoàn thành: synced=%d, failed=%d, total_missing=%d.",
            synced,
            failed,
            total_missing,
        )
        return {"synced": synced, "failed": failed, "total_missing": total_missing}
