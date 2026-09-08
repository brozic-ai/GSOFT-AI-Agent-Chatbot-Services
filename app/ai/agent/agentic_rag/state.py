from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgenticRagState(TypedDict):
    """State quản lý ngữ cảnh hội thoại và dữ liệu của RAG Knowledge Agent (Fast Pipeline)."""

    # Lịch sử tin nhắn (Human, AI) — add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Câu hỏi gốc (dùng bởi retrieve_rag_node & generator_node)
    user_query: str

    # Mã phiên làm việc
    session_id: str

    # RBAC context (truyền cho VectorRetriever phân quyền tài liệu)
    user_roles: Optional[str]
    user_department: Optional[str]

    # Retrieval state (retrieve_rag_node set các giá trị này qua Hybrid Search + BGE Cross-Encoder)
    documents: list[str]
    citations: list[dict[str, Any]]
    is_relevant: bool

    # Output tổng hợp cuối cùng từ generator_node
    final_answer: str

