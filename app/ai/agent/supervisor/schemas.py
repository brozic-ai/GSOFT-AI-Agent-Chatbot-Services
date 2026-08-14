from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FAQ = "faq"
    RAG = "rag"
    GAMSPRO = "gamspro"
    FALLBACK = "fallback"


class RouterOutput(BaseModel):
    reasoning: str = Field(description="Lý do suy luận chi tiết bằng tiếng Việt trước khi đưa ra quyết định phân loại intent")
    intent: IntentType = Field(description="Intent classification (faq, rag, gamspro, fallback)")
    query: str = Field(description="Optimized query for the tool")
    confidence: float = Field(description="Confidence score of the intent (0.85 - 1.00)")
