import json
import logging
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_doc_repo = None


def _get_doc_repo():
    global _doc_repo
    if _doc_repo is None:
        from app.routers.dependencies import get_repository

        _doc_repo = get_repository()
    return _doc_repo


class DocMetadataInput(BaseModel):
    doc_id: Optional[int] = Field(
        default=None, description="ID định danh tài liệu trong hệ thống RAG"
    )
    file_name: Optional[str] = Field(
        default=None,
        description="Tên file tài liệu (ví dụ: 'HDSD Phan mem QLTS GD 1-2-3 - DANH MUC - HE THONG.docx')",
    )


@tool("get_document_metadata", args_schema=DocMetadataInput)
async def get_document_metadata(
    doc_id: Optional[int] = None, file_name: Optional[str] = None
) -> str:
    """Tra cứu thông tin metadata của tài liệu quy chế/HDSD trong hệ thống RAG.

    Bao gồm tên tài liệu, loại tài liệu, ngày ban hành, phòng ban quản lý và phạm vi truy cập.
    """
    try:
        repo = _get_doc_repo()
        if doc_id is not None:
            doc = repo.get_rag_document_by_id(doc_id)
            if not doc:
                return json.dumps(
                    {"error": f"Không tìm thấy tài liệu có ID {doc_id}"},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "id": doc.id,
                    "document_name": doc.document_name,
                    "file_name": doc.file_name,
                    "category": doc.category,
                    "owner_department": doc.owner_department,
                    "access_scope": doc.access_scope,
                    "effective_date": str(doc.effective_date)
                    if doc.effective_date
                    else None,
                    "expiration_date": str(doc.expiration_date)
                    if doc.expiration_date
                    else None,
                },
                ensure_ascii=False,
            )
        elif file_name:
            docs = repo.search_rag_documents(query=file_name, limit=5)
            if not docs:
                return json.dumps(
                    {"error": f"Không tìm thấy tài liệu khớp với '{file_name}'"},
                    ensure_ascii=False,
                )
            results = [
                {
                    "id": d.id,
                    "document_name": d.document_name,
                    "file_name": d.file_name,
                    "category": d.category,
                    "owner_department": d.owner_department,
                    "access_scope": d.access_scope,
                }
                for d in docs
            ]
            return json.dumps({"results": results}, ensure_ascii=False)
        else:
            return json.dumps(
                {"error": "Vui lòng cung cấp doc_id hoặc file_name để tra cứu"},
                ensure_ascii=False,
            )
    except Exception as e:
        logger.exception("get_document_metadata error")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
