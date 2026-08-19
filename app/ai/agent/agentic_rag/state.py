from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgenticRagState(TypedDict):
    """State quản lý ngữ cảnh hội thoại và dữ liệu của RAG Knowledge Agent."""

    # Lịch sử tin nhắn (Human, AI, ToolMessage) — add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Câu hỏi gốc (dùng bởi grader_node & generator_node, không thay đổi sau retry)
    user_query: str

    # Mã phiên làm việc
    session_id: str

    # RBAC context (truyền cho VectorRetriever phân quyền tài liệu)
    user_roles: Optional[str]
    user_department: Optional[str]

    # Retrieval state (grader_node set các giá trị này)
    documents: list[str]
    citations: list[dict[str, Any]]
    is_relevant: bool
    retry_count: int  # Max = 2, chống loop vô hạn

    # Output
    final_answer: str
