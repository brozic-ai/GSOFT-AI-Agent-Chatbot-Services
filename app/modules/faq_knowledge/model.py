"""
SQLAlchemy ORM Model cho bảng FAQ Knowledge Base.
Lưu trữ các cặp câu hỏi - câu trả lời phục vụ FAQ Agent.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)

from app.core.database import Base


class FaqKnowledge(Base):
    """Bảng lưu trữ câu hỏi - câu trả lời thường gặp (FAQ Knowledge Base)."""

    __tablename__ = "FAQ_Knowledge_Base"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)

    question = Column(
        "Question",
        UnicodeText,
        nullable=False,
        comment="Nội dung câu hỏi gốc (lưu nguyên văn bản người dùng nhập).",
    )

    question_normalized = Column(
        "QuestionNormalized",
        Unicode(450),
        nullable=False,
        comment="Câu hỏi đã chuẩn hóa (lowercase, strip, max 450 ký tự) dùng để kiểm tra trùng lặp.",
    )

    answer = Column(
        "Answer",
        UnicodeText,
        nullable=False,
        comment="Câu trả lời chi tiết cho câu hỏi.",
    )

    category = Column(
        "Category",
        Unicode(200),
        nullable=True,
        comment="Phân loại / chủ đề của câu hỏi (VD: eOffice, VPP, Nhân sự).",
    )

    metadata_json = Column(
        "Metadata",
        UnicodeText,
        nullable=True,
        comment="Metadata bổ sung dưới dạng JSON (source, tags, author, ...).",
    )

    created_at = Column(
        "CreatedAt",
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Thời điểm tạo bản ghi.",
    )

    updated_at = Column(
        "UpdatedAt",
        DateTime,
        nullable=True,
        onupdate=datetime.utcnow,
        comment="Thời điểm cập nhật gần nhất.",
    )

    __table_args__ = (
        # Ràng buộc UNIQUE trên trường chuẩn hóa để chống trùng lặp ở cấp Database
        UniqueConstraint("QuestionNormalized", name="UQ_FAQ_QuestionNormalized"),
        # Index tăng tốc tìm kiếm theo category
        Index("IX_FAQ_Category", "Category"),
    )

    def __repr__(self) -> str:
        return f"<FaqKnowledge id={self.id} category='{self.category}'>"
