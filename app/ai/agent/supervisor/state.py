from pydantic import BaseModel, Field

from app.ai.agent.supervisor.schemas import RouterOutput


class SupervisorState(BaseModel):
    session_id: str = Field(default="eval-session", description="ID phiên làm việc")
    user_query: str = Field(description="Câu hỏi của người dùng")
    chat_history: list[dict] = Field(default_factory=list, description="Lịch sử hội thoại")
    route: RouterOutput | None = Field(default=None, description="Kết quả phân loại intent từ LLM")
