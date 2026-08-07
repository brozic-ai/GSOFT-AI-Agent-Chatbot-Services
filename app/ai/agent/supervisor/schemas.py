from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class IntentType(str, Enum):
    FAQ = "faq"
    RAG = "rag"
    GENERAL = "general"

class RouterOutput(BaseModel):
    intent: IntentType = Field(description="Intent classification")
    query: str = Field(description="Optimized query for the tool")
    confidence: float = Field(description="Confidence score of the intent")
    reasoning: str = Field(description="Reasoning for the intent classification")