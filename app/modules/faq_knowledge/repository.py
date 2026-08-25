"""
FAQ Knowledge Base Repository: Tầng truy xuất dữ liệu từ Database.
Tách biệt hoàn toàn logic tương tác DB ra khỏi Service và API.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.faq_knowledge.model import FaqKnowledge

logger = logging.getLogger(__name__)


def _normalize_question(question: str) -> str:
    """Chuẩn hóa chuỗi câu hỏi: lowercase, strip khoảng trắng thừa."""
    return " ".join(question.strip().lower().split())


class FaqRepository:
    """Repository xử lý các thao tác CRUD với bảng FAQ_Knowledge_Base."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------------
    def create(
        self,
        question: str,
        answer: str,
        category: str | None = None,
        metadata_json: str | None = None,
    ) -> FaqKnowledge:
        """Tạo mới 1 bản ghi FAQ. Caller chịu trách nhiệm commit."""
        normalized = _normalize_question(question)
        faq = FaqKnowledge(
            question=question.strip(),
            question_normalized=normalized,
            answer=answer.strip(),
            category=category,
            metadata_json=metadata_json,
        )
        self.db.add(faq)
        return faq

    # -------------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------------
    def get_by_id(self, faq_id: int) -> FaqKnowledge | None:
        """Lấy 1 FAQ theo ID."""
        return self.db.get(FaqKnowledge, faq_id)

    def get_all(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> tuple[list[FaqKnowledge], int]:
        """Lấy danh sách FAQ có phân trang, hỗ trợ lọc theo category.
        
        Returns:
            Tuple (danh sách FAQ, tổng số bản ghi).
        """
        stmt = select(FaqKnowledge)
        count_stmt = select(func.count()).select_from(FaqKnowledge)

        if category:
            stmt = stmt.where(FaqKnowledge.category == category)
            count_stmt = count_stmt.where(FaqKnowledge.category == category)

        total = self.db.execute(count_stmt).scalar_one()

        stmt = (
            stmt.order_by(FaqKnowledge.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(self.db.execute(stmt).scalars())
        return items, total

    def get_by_normalized_question(self, question: str) -> FaqKnowledge | None:
        """Kiểm tra câu hỏi đã tồn tại (sau chuẩn hóa) để tránh trùng lặp."""
        normalized = _normalize_question(question)
        stmt = select(FaqKnowledge).where(
            FaqKnowledge.question_normalized == normalized
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def exists_normalized(self, question: str) -> bool:
        """Trả về True nếu câu hỏi (sau chuẩn hóa) đã tồn tại trong DB."""
        return self.get_by_normalized_question(question) is not None

    # -------------------------------------------------------------------------
    # UPDATE
    # -------------------------------------------------------------------------
    def update(
        self,
        faq: FaqKnowledge,
        question: str | None = None,
        answer: str | None = None,
        category: str | None = None,
        metadata_json: str | None = None,
    ) -> FaqKnowledge:
        """Cập nhật thông tin FAQ. Caller chịu trách nhiệm commit."""
        if question is not None:
            faq.question = question.strip()
            faq.question_normalized = _normalize_question(question)
        if answer is not None:
            faq.answer = answer.strip()
        if category is not None:
            faq.category = category
        if metadata_json is not None:
            faq.metadata_json = metadata_json
        return faq

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------
    def delete(self, faq: FaqKnowledge) -> None:
        """Xóa 1 FAQ khỏi DB. Caller chịu trách nhiệm commit."""
        self.db.delete(faq)
