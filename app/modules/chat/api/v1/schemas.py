"""
Pydantic Schemas cho phân hệ Chatbot RAG (SSE Chat Stream).
"""


from pydantic import BaseModel, Field


class ChatImageInput(BaseModel):
    fileName: str
    contentType: str
    base64: str


class ChatRequest(BaseModel):
    message: str = ""
    images: list[ChatImageInput] = Field(default_factory=list)
    user_roles: str | None = Field(
        default=None,
        alias="user_roles",
        description="Danh sách Vai trò của user, phân cách bằng dấu phẩy",
    )
    conversation_id: str | None = Field(default=None, alias="conversation_id")

    model_config = {"populate_by_name": True}
