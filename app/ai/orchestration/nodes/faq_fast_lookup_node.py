"""
FAQ Fast-Path Lookup Node — Tra cứu FAQ siêu tốc bằng Exact Match hoặc Vector Similarity (Zero-LLM Latency).

Trước khi gọi Classify Intent và RAG:
- Nếu câu hỏi khớp 100% (Exact Match) hoặc Cosine Similarity >= 90% (0.90):
  -> Trả về ngay câu trả lời FAQ, đính kèm citations, bỏ qua Classify Intent, bỏ qua LLM và RAG.
  -> Thời gian phản hồi chỉ ~20-50ms.
- Nếu không khớp hoặc similarity < 90%:
  -> Tiếp tục chuyển sang classify_intent để xử lý thông thường.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage

from app.ai.agent.faq.services.faq_retriever import find_fast_faq_match
from app.ai.agent.supervisor.schemas import IntentType, RouterOutput
from app.ai.orchestration.state import OrchestratorState

logger = logging.getLogger(__name__)


async def faq_fast_lookup_node(state: OrchestratorState) -> Dict[str, Any]:
    """Node thực thi tra cứu FAQ siêu tốc trước khi gọi phân loại Intent."""
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )

    if not user_query:
        messages = (
            list(state.get("messages", []))
            if isinstance(state, dict)
            else list(getattr(state, "messages", []))
        )
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or getattr(msg, "type", "") == "human":
                user_query = str(msg.content).strip()
                break

    if not user_query:
        return {"faq_fast_match": False}

    logger.debug("[FAQ FAST-LOOKUP] Kiểm tra Fast-path cho: '%s'", user_query[:80])
    match_result = await find_fast_faq_match(user_query)

    if match_result and match_result.get("found"):
        answer = match_result["answer"]
        score = match_result.get("score", 1.0)
        match_type = match_result.get("match_type", "exact")
        citations = match_result.get("citations", [])

        logger.info(
            "[FAQ FAST-LOOKUP] [HIT] Tìm thấy FAQ Fast-Match (%s, score=%.4f). Bỏ qua Classify Intent & LLM.",
            match_type,
            score,
        )

        route_obj = RouterOutput(
            reasoning=f"Tra cứu khớp trực tiếp kho FAQ bằng {match_type} (Zero-LLM)",
            intent=IntentType.FAQ,
            query=user_query,
            confidence=score,
        )

        return {
            "faq_fast_match": True,
            "agent_output": answer,
            "final_answer": answer,
            "citations": citations,
            "route": route_obj,
            "intent": "faq",
            "messages": [AIMessage(content=answer)],
        }

    return {"faq_fast_match": False}
