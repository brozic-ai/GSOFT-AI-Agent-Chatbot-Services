"""
Pydantic Schemas cho phân hệ Chatbot RAG (SSE Chat Stream & Conversation History).
"""


from typing import Optional, List, Union
from pydantic import BaseModel, Field


class ChatImageInput(BaseModel):
    fileName: str
    contentType: str
    base64: str


class ChatRequest(BaseModel):
    message: str = ""
    images: List[ChatImageInput] = Field(default_factory=list)
    user_roles: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Danh sách Vai trò của user. Runtime xác thực ưu tiên header X-User-Roles.",
        json_schema_extra={"deprecated": True},
    )
    user_department: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Phòng ban của user. Runtime xác thực ưu tiên header X-User-Department.",
        json_schema_extra={"deprecated": True},
    )
    user_id: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] ID người dùng. Runtime bắt buộc truyền qua header X-User-Id.",
        json_schema_extra={"deprecated": True},
    )
    conversation_id: Optional[Union[str, int]] = Field(default=None, description="ID phiên hội thoại. Nếu None, bot sẽ trả lời không lưu lịch sử.")

    model_config = {
        "populate_by_name": True
    }


class ConversationCreateResponse(BaseModel):
    """Response khi tạo phiên hội thoại mới."""
    conversation_id: Union[str, int]
    title: str
    message: str = "Phiên hội thoại mới đã được tạo thành công."


class ConversationResponse(BaseModel):
    """Response thông tin một phiên hội thoại."""
    id: Union[str, int]
    title: str
    is_pinned: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    time_label: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    is_pinned: Optional[bool] = None


class ChatMessageResponse(BaseModel):
    """Response thông tin một tin nhắn trong phiên hội thoại."""
    id: int
    role: str
    content: str
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
