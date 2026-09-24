from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FAQ = "faq"
    RAG = "rag"
    PROCUREMENT = "procurement"
    FALLBACK = "fallback"


class RouterOutput(BaseModel):
    reasoning: str = Field(description="1 câu ngắn gọn giải thích lý do bằng tiếng Việt trước khi đưa ra quyết định phân loại intent")
    intent: IntentType = Field(description="Intent classification (faq, rag, procurement, fallback)")
    query: str = Field(description="Optimized query for the tool")
    confidence: float = Field(description="Confidence score of the intent (0.85 - 1.00)")
