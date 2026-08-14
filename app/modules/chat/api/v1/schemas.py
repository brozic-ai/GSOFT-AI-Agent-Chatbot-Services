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
    user_roles: Optional[str] = Field(default=None, description="Danh sách Vai trò của user, phân cách bằng dấu phẩy")
    conversation_id: Optional[int] = Field(default=None, description="ID phiên hội thoại (int). Nếu None, bot sẽ trả lời không lưu lịch sử.")

    model_config = {
        "populate_by_name": True
    }


class ConversationCreateResponse(BaseModel):
    """Response khi tạo phiên hội thoại mới."""
    conversation_id: int
    title: str
    message: str = "Phiên hội thoại mới đã được tạo thành công."


class ConversationResponse(BaseModel):
    """Response thông tin một phiên hội thoại."""
    id: int
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
