from pydantic import BaseModel, Field

class ContextualizedQuery(BaseModel):
    resolved_query: str                             # câu hỏi đã viết lại (hoặc giữ nguyên nếu confidence thấp)
    confidence: float = Field(..., ge=0, le=1)
    context_resolved: bool                          # True nếu đã dùng lịch sử để viết lại thành công