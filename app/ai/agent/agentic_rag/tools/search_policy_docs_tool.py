import json
import logging
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_retriever = None  # Module-level singleton


def _get_retriever():
    global _retriever
    if _retriever is None:
        from app.routers.dependencies import get_vector_retriever

        _retriever = get_vector_retriever()
    return _retriever


# ── Module-level RBAC context (set bởi entrypoint trước khi gọi graph) ──
_rbac_context: dict[str, str | None] = {"user_roles": None, "user_department": None}


def set_rbac_context(
    user_roles: str | None = None, user_department: str | None = None
) -> None:
    """Gọi trước khi invoke graph để truyền RBAC vào tool."""
    _rbac_context["user_roles"] = user_roles
    _rbac_context["user_department"] = user_department


class SearchPolicyDocsInput(BaseModel):
    query: str = Field(
        description="Câu hỏi hoặc từ khóa tra cứu quy chế, chính sách, HDSD gAMSPro"
    )
    top_k: int = Field(default=5, description="Số lượng đoạn văn bản trả về (1-10)")


async def _search_policy_and_manual_docs_impl(
    query: str, top_k: int = 5
) -> str:
    """Hàm thực thi tra cứu ngữ cảnh tài liệu quy chế và HDSD."""
    try:
        retriever = _get_retriever()
        result = await retriever.retrieve_context(
            query=query,
            top_k=top_k,
            user_roles=_rbac_context.get("user_roles"),
            user_department=_rbac_context.get("user_department"),
        )
        documents = (
            result.get("documents", [[]])[0] if result.get("documents") else []
        )
        citations = (
            result.get("citations", [[]])[0] if result.get("citations") else []
        )
        return json.dumps(
            {"documents": documents, "citations": citations}, ensure_ascii=False
        )
    except Exception as e:
        logger.exception("search_policy_and_manual_docs error")
        return json.dumps({"documents": [], "citations": [], "error": str(e)})


@tool("search_policy_and_manual_docs", args_schema=SearchPolicyDocsInput)
async def search_policy_and_manual_docs(query: str, top_k: int = 5) -> str:
    """Tìm kiếm trong kho tài liệu quy chế, chính sách nội bộ, sổ tay HDSD gAMSPro.

    Dùng tool này khi cần tra cứu quy trình, thủ tục, điều kiện nghiệp vụ từ văn bản.
    """
    return await _search_policy_and_manual_docs_impl(query=query, top_k=top_k)


@tool("vector_search_tool", args_schema=SearchPolicyDocsInput)
async def vector_search_tool(query: str, top_k: int = 5) -> str:
    """Công cụ tìm kiếm ngữ nghĩa Vector Search trong kho dữ liệu tài liệu chính sách, quy chế và HDSD gAMSPro.

    Tra cứu các đoạn tài liệu liên quan phù hợp nhất kèm phân quyền truy cập RBAC.
    """
    return await _search_policy_and_manual_docs_impl(query=query, top_k=top_k)


