from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ProcurementState(TypedDict, total=False):
    """State quản lý ngữ cảnh hội thoại và dữ liệu của Procurement Agent."""

    # Lịch sử tin nhắn hội thoại đa lượt (Human, AI, Tool Messages) tự động merge qua add_messages
    messages: Annotated[list[BaseMessage], add_messages]

    # Username của cán bộ đang đăng nhập / tương tác
    user_name: str

    # Mã định danh phiên làm việc / hội thoại
    session_id: str

    # Loại định tuyến từ Router Node ("tool_call", "need_info", "direct_answer")
    route_type: Optional[str]

    # Danh sách các trường thông tin còn thiếu khi router trả về need_info
    missing_fields: Optional[list[str]]
