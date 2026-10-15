from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FAQ = "faq"
    RAG = "rag"
    PROCUREMENT = "procurement"
    FALLBACK = "fallback"


class RouterOutput(BaseModel):
    reasoning: str = Field(description="1 câu ngắn gọn giải thích lý do bằng tiếng Việt trước khi đưa ra quyết định phân loại intent")
    in_scope: bool = Field(default=True, description="True ONLY for BVBank/company work, HR, manuals or procurement. False for unrelated general knowledge such as geography/capitals, entertainment or science.")
    intent: IntentType = Field(description="Intent classification (faq, rag, procurement, fallback)")
    query: str = Field(description="Optimized query for the tool")
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False, description="Confidence score of the intent (0.00 - 1.00)")
