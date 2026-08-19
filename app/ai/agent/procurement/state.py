from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ProcurementState(TypedDict):
    """State quản lý ngữ cảnh hội thoại và dữ liệu của Procurement Agent."""

    # Lịch sử tin nhắn hội thoại đa lượt (Human, AI, Tool Messages) tự động merge qua add_messages
    messages: Annotated[list[BaseMessage], add_messages]

    # Username của cán bộ đang đăng nhập / tương tác (lấy từ Session/Header, fallback 'baotq')
    user_name: str

    # Mã định danh phiên làm việc / hội thoại
    session_id: str
