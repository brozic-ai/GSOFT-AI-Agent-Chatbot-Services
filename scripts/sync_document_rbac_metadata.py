"""
Script đồng bộ quyền hạn truy cập (RBAC Metadata) từ bảng RagDocuments và RagDocumentRoles
xuống toàn bộ các Chunks vector trong bảng Documents.

Chạy định kỳ hoặc khi có nhu cầu đồng bộ dữ liệu:
    uv run python scripts/sync_document_rbac_metadata.py
"""

import logging
import os
import sys

# Đảm bảo đường dẫn import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.document.model import RagDocument, RagDocumentRole
from app.modules.document.repository import DocumentRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_document_rbac")


def sync_all_document_rbac():
    logger.info("=== Bắt đầu đồng bộ quyền hạn RBAC cho toàn bộ tài liệu ===")
    repo = DocumentRepository()
    db: Session = SessionLocal()

    try:
        documents = db.query(RagDocument).all()
        logger.info("Tìm thấy %d tài liệu trong RagDocuments.", len(documents))

        total_chunks_synced = 0
        doc_count = 0

        for doc in documents:
            doc_id = doc.id
            access_scope = doc.access_scope or "Public"
            owner_dept = doc.owner_department
            category = doc.category

            # Lấy danh sách roles
            roles = (
                db.query(RagDocumentRole.role_name)
                .filter(RagDocumentRole.rag_document_id == doc_id)
                .all()
            )
            role_names = [r[0].strip() for r in roles if r[0] and r[0].strip()]

            # Nếu là NVPT hoặc role GUID tương ứng của NVPT, bổ sung cả hai để tránh lệch chuẩn
            expanded_roles = set(role_names)
            for r in role_names:
                if r == "ecb5501c5b884794a3d4bf34faa47625":
                    expanded_roles.add("NVPT")
                elif r.upper() == "NVPT":
                    expanded_roles.add("ecb5501c5b884794a3d4bf34faa47625")

            final_roles = list(expanded_roles)

            chunks_updated = repo.sync_document_chunks_metadata(
                backend_id=doc_id,
                access_scope=access_scope,
                owner_department=owner_dept,
                allowed_roles=final_roles,
                category=category,
            )

            total_chunks_synced += chunks_updated
            doc_count += 1
            logger.info(
                "[%d/%d] Doc ID=%d | '%s' | Scope=%s | Dept=%s | Roles=%s -> Cập nhật %d chunks",
                doc_count,
                len(documents),
                doc_id,
                doc.document_name,
                access_scope,
                owner_dept,
                final_roles,
                chunks_updated,
            )

        logger.info(
            "=== Hoàn tất đồng bộ! Tổng cộng %d tài liệu, %d chunks vector đã được cập nhật metadata RBAC ===",
            doc_count,
            total_chunks_synced,
        )

    except Exception as ex:
        logger.exception("Lỗi trong quá trình đồng bộ RBAC: %s", ex)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sync_all_document_rbac()
