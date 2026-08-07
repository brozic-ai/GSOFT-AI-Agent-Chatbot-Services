from typing import Optional
from pydantic import BaseModel, Field
from app.ai.agent.supervisor.schemas import RouterOutput


class SupervisorState(BaseModel):
    session_id: str
    user_query: str
    chat_history: list[dict] = Field(default_factory=list)
    route: Optional[RouterOutput] = None