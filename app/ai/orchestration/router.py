"""
Router & Conditional Edges trong Orchestrator Graph.
"""

import logging
import math
from typing import Any, Dict

from app.ai.agent.supervisor.schemas import IntentType

logger = logging.getLogger(__name__)


def route_after_input_guardrail(state: Any) -> str:
    """
    Rẽ nhánh sau khi kiểm tra Input Guardrail:
    - Nếu vi phạm quy tắc an toàn -> chuyển thẳng đến 'output_guardrail' để xuất thông báo an toàn.
    - Nếu hợp lệ -> chuyển sang 'faq_fast_lookup' để kiểm tra câu hỏi khớp siêu tốc.
    """
    guardrail_res = state.get("guardrail_result") if isinstance(state, dict) else getattr(state, "guardrail_result", None)
    if guardrail_res and not getattr(guardrail_res, "is_safe", True):
        logger.info("[ROUTER] Câu hỏi vi phạm Guardrail -> Chuyển thẳng sang output_guardrail.")
        return "output_guardrail"

    return "faq_fast_lookup"


def route_after_faq_fast_lookup(state: Any) -> str:
    """
    Rẽ nhánh sau khi tra cứu FAQ siêu tốc (Exact Match / Vector Similarity >= 90%):
    - Nếu khớp -> chuyển thẳng sang 'output_guardrail' (bỏ qua classify_intent và RAG, thời gian ~20-50ms).
    - Nếu không khớp -> chuyển sang 'classify_intent' để LLM phân loại ý định bình thường.
    """
    is_fast_matched = state.get("faq_fast_match", False) if isinstance(state, dict) else getattr(state, "faq_fast_match", False)
    if is_fast_matched:
        logger.info("[ROUTER] [FAST-PATH HIT] Khớp FAQ siêu tốc -> Bỏ qua Classify Intent & LLM, sang output_guardrail.")
        return "output_guardrail"

    return "classify_intent"


def route_after_classification(state: Any) -> str:
    """
    Rẽ nhánh sau khi phân loại ý định (Intent):
    - procurement -> 'procurement_agent'
    - rag -> 'rag_agent'
    - faq -> 'faq_agent'
    - fallback -> 'fallback_agent'
    """
    route = state.get("route") if isinstance(state, dict) else getattr(state, "route", None)
    if not route:
        logger.warning("[ROUTER] Không có kết quả phân loại -> Chuyển sang fallback_agent.")
        return "fallback_agent"

    raw_intent = route.intent if hasattr(route, "intent") else route.get("intent", "")
    if hasattr(raw_intent, "value"):
        intent_str = str(raw_intent.value).lower()
    else:
        intent_str = str(raw_intent).lower()

    confidence = route.get("confidence", 0.0) if isinstance(route, dict) else getattr(route, "confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return "fallback_agent"
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return "fallback_agent"

    # Nếu độ tin cậy quá thấp (< 0.5) -> Fallback
    if confidence < 0.5:
        logger.warning("[ROUTER] Độ tin cậy thấp (%s) -> Chuyển sang fallback_agent.", confidence)
        return "fallback_agent"

    if intent_str == "procurement":
        return "procurement_agent"
    elif intent_str == "rag":
        return "rag_agent"
    elif intent_str == "faq":
        return "faq_agent"
    else:
        return "fallback_agent"
