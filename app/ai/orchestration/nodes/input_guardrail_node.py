"""Input Guardrail Node trong Orchestrator."""
import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage
from app.ai.guardrails.guardrail import InputGuardrail, SAFE_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)


async def input_guardrail_node(state: Any) -> Dict[str, Any]:
    """
    Kiểm tra câu hỏi người dùng ở tầng Input Guardrail.
    Nếu vi phạm -> gắn cờ và trả về câu Fallback an toàn.
    """
    user_query = state.get("user_query", "") if isinstance(state, dict) else getattr(state, "user_query", "")
    guardrail_result = InputGuardrail.validate(user_query)

    if not guardrail_result.is_safe:
        logger.warning(
            "[ORCHESTRATOR GUARDRAIL] Chặn câu hỏi vi phạm: '%s' (Lý do: %s)",
            user_query[:80],
            guardrail_result.violation_type,
        )
        return {
            "guardrail_result": guardrail_result,
            "agent_output": SAFE_FALLBACK_MESSAGE,
            "messages": [AIMessage(content=SAFE_FALLBACK_MESSAGE)],
        }

    return {"guardrail_result": guardrail_result}
