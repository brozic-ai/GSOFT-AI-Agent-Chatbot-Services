"""
SQLAlchemy ORM Models cho phân hệ Quản lý Tài liệu (Document Management & RBAC).
Khớp với thiết kế bảng Cơ sở dữ liệu gAMSPro (dbo.RagDocuments & dbo.RagDocumentRoles).

Lưu ý: Bảng `Documents` (lưu Vector Chunks VECTOR(1024)) KHÔNG được định nghĩa là ORM Model
vì SQLAlchemy không có kiểu VECTOR native trên SQL Server.
Bảng này được tạo bởi DDL script trong lifespan startup (app/lifespan.py).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class RagDocument(Base):
    """Bảng lưu thông tin siêu dữ liệu tài liệu RAG."""

    __tablename__ = "RagDocuments"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    document_name = Column("DocumentName", Unicode(500), nullable=False)
    file_name = Column("FileName", Unicode(500), nullable=False)
    file_path = Column("FilePath", Unicode(1000), nullable=False)
    file_size = Column("FileSize", BigInteger, nullable=False)
    category = Column("Category", Unicode(200), nullable=True)
    owner_department = Column("OwnerDepartment", Unicode(200), nullable=True)
    description = Column("Description", UnicodeText, nullable=True)
    tags = Column("Tags", UnicodeText, nullable=True)  # Chuỗi JSON chứa mảng tag
    access_scope = Column(
        "AccessScope", String(50), nullable=False, default="Public"
    )  # 'Public' hoặc 'Restricted'
    effective_date = Column("EffectiveDate", DateTime, nullable=True)
    expiration_date = Column("ExpirationDate", DateTime, nullable=True)
    ingest_status = Column(
        "IngestStatus", String(50), nullable=False, default="Pending"
    )  # 'Pending', 'Processing', 'Completed', 'Failed'
    ingest_error = Column("IngestError", UnicodeText, nullable=True)
    chunk_count = Column("ChunkCount", Integer, nullable=False, default=0)
    uploaded_by = Column("UploadedBy", Unicode(100), nullable=True)
    tenant_id = Column("TenantId", Integer, nullable=True)
    creation_time = Column(
        "CreationTime", DateTime, nullable=False, default=datetime.utcnow
    )
    last_modification_time = Column("LastModificationTime", DateTime, nullable=True)

    # Quan hệ 1-N tới danh sách Vai trò được truy cập
    roles = relationship(
        "RagDocumentRole", back_populates="document", cascade="all, delete-orphan"
    )


class RagDocumentRole(Base):
    """Bảng lưu cấu hình Vai trò (Role) được truy cập tài liệu có mức độ Restricted."""

    __tablename__ = "RagDocumentRoles"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    rag_document_id = Column(
        "RagDocumentId",
        Integer,
        ForeignKey("RagDocuments.Id", ondelete="CASCADE"),
        nullable=False,
    )
    role_name = Column("RoleName", Unicode(200), nullable=False)

    document = relationship("RagDocument", back_populates="roles")


# Đánh chỉ mục Index cho vai trò
Index("IX_RagDocumentRoles_RagDocumentId", RagDocumentRole.rag_document_id)
