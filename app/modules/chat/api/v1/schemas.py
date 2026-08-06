"""
Pydantic Schemas cho phân hệ Chatbot RAG (SSE Chat Stream & Conversations Management).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ChatImageInput(BaseModel):
    fileName: str
    contentType: str
    base64: str


class ChatRequest(BaseModel):
    message: str = ""
    images: List[ChatImageInput] = Field(default_factory=list)
    user_roles: Optional[str] = Field(default=None, alias="user_roles", description="Danh sách Vai trò của user, phân cách bằng dấu phẩy")
    user_department: Optional[str] = Field(default=None, alias="user_department", description="Phòng ban của user")
    conversation_id: Optional[str] = Field(default=None, alias="conversation_id", description="ID Phiên trò chuyện")
    user_id: Optional[str] = Field(default=None, alias="user_id", description="ID Người dùng")

    model_config = {
        "populate_by_name": True
    }


class ConversationResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: Optional[str] = None
    creation_time: Optional[str] = None
    updated_time: Optional[str] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationResponse]
    total_count: int


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    citations: Optional[str] = None
    creation_time: Optional[str] = None
