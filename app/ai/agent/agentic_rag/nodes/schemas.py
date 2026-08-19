from pydantic import BaseModel, Field


class DocumentGradeOutput(BaseModel):
    """Kết quả đánh giá chất lượng và độ liên quan của tài liệu thu được từ RAG."""

    is_relevant: bool = Field(
        description="True nếu tài liệu chứa thông tin liên quan hoặc đủ để trả lời câu hỏi của người dùng, False nếu không liên quan"
    )
    reasoning: str = Field(
        description="Lý giải ngắn gọn bằng tiếng Việt về lý do tài liệu liên quan hoặc không liên quan"
    )
