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


class ListPolicyCategoriesInput(BaseModel):
    category_filter: Optional[str] = Field(
        default=None,
        description="Lọc theo nhóm nghiệp vụ hoặc từ khóa danh mục (ví dụ: 'QLTS', 'Mua sắm', 'Quy chế')",
    )


@tool("list_policy_categories", args_schema=ListPolicyCategoriesInput)
async def list_policy_categories(category_filter: Optional[str] = None) -> str:
    """Liệt kê các nhóm danh mục chính sách, quy chế và sổ tay HDSD hiện có trong hệ thống BVBank & gAMSPro.

    Dùng tool này khi người dùng muốn biết hệ thống có những tài liệu hướng dẫn hoặc quy chế nào.
    """
    try:
        repo = _get_doc_repo()
        docs = repo.get_rag_documents_list()
        
        categories: dict[str, list[dict[str, str]]] = {}
        for d in docs:
            cat = d.get("category") or "Quy chế & HDSD Chung"
            if category_filter and category_filter.lower() not in cat.lower() and category_filter.lower() not in (d.get("document_name") or "").lower():
                continue
            
            if cat not in categories:
                categories[cat] = []
            
            categories[cat].append({
                "id": str(d.get("id", "")),
                "document_name": d.get("document_name") or d.get("file_name") or "",
                "owner_department": d.get("owner_department") or "BVBank",
                "access_scope": d.get("access_scope") or "Public",
            })
            
        summary = []
        for cat, items in categories.items():
            summary.append({
                "category": cat,
                "document_count": len(items),
                "documents": items[:5],  # Top 5 per category
            })
            
        return json.dumps({"categories": summary, "total_categories": len(summary)}, ensure_ascii=False)
    except Exception as e:
        logger.exception("list_policy_categories error")
        return json.dumps({"categories": [], "error": str(e)}, ensure_ascii=False)
