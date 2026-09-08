"""
Script Re-indexing & Cleaning RAG Documents (scripts/reindex_documents.py).

Chức năng:
1. Dọn dẹp các chunk rác nhị phân (như tài liệu 1055, 1057).
2. Xóa các vector chunks cũ bị băm vụn (600 chars) của tài liệu PPTX / DOCX.
3. Tái lập chỉ mục (Re-ingest) theo chuẩn kiến trúc mới:
   - Atomic Slide Extraction (1 Slide = 1 Vector, có nhãn ### Tiêu đề: ...)
   - Slide Aggregation (gộp slide < 200 ký tự vào slide kế tiếp)
   - Token Chunker (800 tokens, 100 overlap)
   - Đảm bảo Vector Index SQL Server 2025 được tái tạo chuẩn xác.

Cách dùng:
  python scripts/reindex_documents.py --clean-binary       # Dọn rác 1055/1057
  python scripts/reindex_documents.py --id 2072           # Reindex riêng 1 tài liệu (test)
  python scripts/reindex_documents.py --type pptx         # Reindex toàn bộ PPTX
  python scripts/reindex_documents.py --all               # Reindex toàn bộ tài liệu
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

# Thêm app vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.ingestion.pipeline import IngestionPipeline
from app.core.database import SessionLocal, engine
from app.modules.document.model import RagDocument
from app.modules.document.repository import DocumentRepository


def clean_binary_junk():
    """Dọn sạch các chunk rác nhị phân của tài liệu 1055 & 1057."""
    print("🧹 [CLEAN] Bắt đầu dọn dẹp các chunk rác nhị phân...")
    repo = DocumentRepository()
    for bid in [1055, 1057]:
        try:
            repo.delete_documents_by_backend_id(bid)
            with SessionLocal() as db:
                doc = db.query(RagDocument).filter(RagDocument.id == bid).first()
                if doc:
                    doc.ingest_status = "Failed"
                    doc.chunk_count = 0
                    doc.ingest_error = "Binary junk cleaned. Ready for proper re-ingestion."
                    db.commit()
            print(f"  ✓ Đã dọn sạch chunks rác cho tài liệu ID {bid}")
        except Exception as ex:
            print(f"  ❌ Lỗi khi dọn rác ID {bid}: {ex}")
    print("✅ [CLEAN] Hoàn tất dọn dẹp rác nhị phân.\n")


def find_file_path(doc: RagDocument) -> str | None:
    """Xác định đường dẫn thực tế của file trên ổ cứng."""
    # 1. Thử đường dẫn lưu trong DB
    if doc.file_path and os.path.exists(doc.file_path):
        return doc.file_path

    # 2. Thử trong thư mục my_documents
    my_doc_path = PROJECT_ROOT / "my_documents" / doc.file_name
    if my_doc_path.exists():
        return str(my_doc_path)

    # 3. Tìm đệ quy trong my_documents
    for p in (PROJECT_ROOT / "my_documents").rglob(doc.file_name):
        if p.exists():
            return str(p)

    return None


async def reindex_single_document(
    doc: RagDocument,
    pipeline: IngestionPipeline,
    repo: DocumentRepository,
) -> bool:
    """Re-index 1 tài liệu với IngestionPipeline mới."""
    file_path = find_file_path(doc)
    if not file_path:
        print(f"  ⚠️ Không tìm thấy file vật lý cho ID={doc.id} ({doc.file_name}). Bỏ qua.")
        return False

    old_chunks = doc.chunk_count or 0
    print(f"\n🔄 [REINDEX] Đang xử lý ID={doc.id}: '{doc.document_name}'")
    print(f"   File: {doc.file_name} (Chunks cũ: {old_chunks})")
    print(f"   Đường dẫn: {file_path}")

    # 1. Xóa chunks cũ trong Documents table
    print("   1. Xóa các vector chunks cũ trong SQL Server...")
    repo.delete_documents_by_backend_id(doc.id, file_name=doc.file_name)

    # 2. Tạo task_id và metadata
    task_id = str(uuid.uuid4())
    metadata = {
        "backend_document_id": doc.id,
        "backendId": doc.id,
        "backend_id": doc.id,
        "category": doc.category,
        "access_scope": doc.access_scope,
        "allowed_roles": [r.role_name for r in doc.roles] if doc.roles else ["Public"],
        "owner_department": doc.owner_department,
    }

    # 3. Đọc nội dung file và tạo file tạm
    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(doc.file_name)[1].lower()
    import tempfile
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as tmp_f:
        with open(file_path, "rb") as src_f:
            tmp_f.write(src_f.read())

    # 4. Chạy IngestionPipeline
    print("   2. Chạy Ingestion Pipeline (Atomic Slide + Token Chunker + Embedding)...")
    try:
        await pipeline._run_async(
            task_id=task_id,
            temp_path=temp_path,
            file_name=doc.file_name,
            file_size=file_size,
            metadata=metadata,
        )

        # 5. Kiểm tra kết quả mới trong DB
        with SessionLocal() as db:
            refreshed = db.query(RagDocument).filter(RagDocument.id == doc.id).first()
            new_chunks = refreshed.chunk_count if refreshed else 0
            new_status = refreshed.ingest_status if refreshed else "Unknown"

        print(f"   ✓ [THÀNH CÔNG] ID={doc.id} -> Status: {new_status} | Số chunks mới: {new_chunks} (Cũ: {old_chunks})")
        return True
    except Exception as ex:
        print(f"   ❌ [THẤT BẠI] Lỗi khi re-index ID={doc.id}: {ex}")
        return False


async def run_reindex(
    target_id: int | None = None,
    file_type: str | None = None,
    reindex_all: bool = False,
):
    """Điều phối reindex theo tham số CLI."""
    from sqlalchemy.orm import selectinload

    repo = DocumentRepository()
    embedding_service = TeiEmbeddingService()
    pipeline = IngestionPipeline(repository=repo, embedding_service=embedding_service)

    with SessionLocal() as db:
        query = db.query(RagDocument).options(selectinload(RagDocument.roles))
        if target_id:
            docs = query.filter(RagDocument.id == target_id).all()
        elif file_type:
            docs = query.filter(RagDocument.file_name.ilike(f"%.{file_type}")).all()
        elif reindex_all:
            docs = query.all()
        else:
            print("Vui lòng chỉ định một tùy chọn: --id <id>, --type <ext>, --all, hoặc --clean-binary")
            return

        # Snapshot danh sách dữ liệu trước khi thoát khỏi Session để tránh DetachedInstanceError
        doc_snapshots = []
        for d in docs:
            doc_snapshots.append(d)

    if not doc_snapshots:
        print("Không tìm thấy tài liệu phù hợp để re-index.")
        return

    print(f"🚀 Bắt đầu Re-indexing cho {len(doc_snapshots)} tài liệu...")
    success_count = 0
    for doc in doc_snapshots:
        ok = await reindex_single_document(doc, pipeline, repo)
        if ok:
            success_count += 1

    print(f"\n==========================================")
    print(f"🎉 HOÀN THÀNH: {success_count}/{len(docs)} tài liệu đã được Re-index thành công!")
    print(f"==========================================")


def main():
    parser = argparse.ArgumentParser(description="Re-index & Clean RAG Documents")
    parser.add_argument("--clean-binary", action="store_true", help="Dọn dẹp các chunk rác nhị phân 1055/1057")
    parser.add_argument("--id", type=int, help="Re-index một tài liệu theo ID")
    parser.add_argument("--type", type=str, help="Re-index các tài liệu theo đuôi file (ví dụ: pptx, docx)")
    parser.add_argument("--all", action="store_true", help="Re-index toàn bộ tài liệu trong CSDL")

    args = parser.parse_args()

    if args.clean_binary:
        clean_binary_junk()

    if args.id or args.type or args.all:
        asyncio.run(
            run_reindex(
                target_id=args.id,
                file_type=args.type,
                reindex_all=args.all,
            )
        )


if __name__ == "__main__":
    main()
