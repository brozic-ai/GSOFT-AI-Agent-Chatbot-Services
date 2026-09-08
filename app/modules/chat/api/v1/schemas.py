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
    user_id: Optional[str] = Field(default=None, description="ID người dùng (fallback nếu không có header)")
    user_roles: Optional[str] = Field(default=None, description="Danh sách Vai trò của user, phân cách bằng dấu phẩy")
    user_department: Optional[str] = Field(default=None, description="Phòng ban của user")
    conversation_id: Optional[int] = Field(default=None, description="ID phiên hội thoại (int). Nếu None, bot sẽ trả lời không lưu lịch sử.")
    is_retry: Optional[bool] = Field(default=False, description="Cờ đánh dấu request tạo lại câu trả lời (Retry in-place)")
    retry_message_id: Optional[int] = Field(default=None, description="ID tin nhắn AI trong DB cần cập nhật lại nội dung")
    is_edit: Optional[bool] = Field(default=False, description="Cờ đánh dấu request chỉnh sửa tin nhắn câu hỏi")
    edit_message_id: Optional[int] = Field(default=None, description="ID tin nhắn User trong DB cần cập nhật")

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
    trace_id: Optional[str] = None
    feedback_score: Optional[int] = None
    feedback_reason: Optional[str] = None
    feedback_comment: Optional[str] = None
    feedback_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ChatFeedbackRequest(BaseModel):
    """Request gửi đánh giá Like/Dislike cho tin nhắn."""
    message_id: int
    score: Optional[int] = Field(None, ge=0, le=1, description="1 cho Like, 0 cho Dislike, None để hủy đánh giá")
    reason: Optional[str] = Field(None, description="Lý do đánh giá (chọn nhanh khi Dislike)")
    comment: Optional[str] = Field(None, description="Ý kiến đóng góp chi tiết")


class ChatFeedbackResponse(BaseModel):
    """Response kết quả ghi nhận đánh giá."""
    success: bool = True
    message: str = "Đã ghi nhận phản hồi thành công."
    data: Optional[dict] = None


class TranscribeResponse(BaseModel):
    """Response kết quả chuyển đổi giọng nói thành văn bản."""
    text: str = Field(..., description="Văn bản đã phiên âm từ giọng nói")
    status: str = Field("success", description="Trạng thái xử lý")
    duration_seconds: Optional[float] = Field(None, description="Thời lượng audio tính theo giây")


