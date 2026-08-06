"""
Pydantic Schemas cho phân hệ Chatbot RAG (SSE Chat Stream).
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
    conversation_id: Optional[str] = Field(default=None, alias="conversation_id")

    model_config = {
        "populate_by_name": True
    }
