"""
FAQ Agent State — Quản lý ngữ cảnh hội thoại cho FAQ Agent.
Kế thừa MessagesState (add_messages reducer) kết hợp các trường tuỳ chỉnh.
"""

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class FAQState(TypedDict):
    """State cho FAQ Agent — quản lý hội thoại và kết quả tìm kiếm FAQ."""

    # Lịch sử tin nhắn (Human, AI, ToolMessage) — add_messages reducer tự động append
    messages: Annotated[list[BaseMessage], add_messages]

    # Câu hỏi gốc từ người dùng (không thay đổi trong suốt luồng)
    user_query: str

    # Mã phiên làm việc
    session_id: str

    # Danh sách FAQ tìm được từ Hybrid Search (do tool trả về, dùng trong logging/debug)
    retrieved_faqs: list[dict]

    # Output cuối cùng để Supervisor đọc
    final_answer: str
