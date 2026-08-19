"""Output Guardrail Node trong Orchestrator."""
import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage
from app.ai.guardrails.guardrail import OutputGuardrail

logger = logging.getLogger(__name__)


async def output_guardrail_node(state: Any) -> Dict[str, Any]:
    """
    Kiểm duyệt nội dung phản hồi của Agent trước khi phát hành về người dùng (Lớp 2 - Output Protection).
    """
    agent_output = state.get("agent_output", "") if isinstance(state, dict) else getattr(state, "agent_output", "")
    sanitized_res = OutputGuardrail.sanitize(agent_output or "")

    if not sanitized_res.is_safe:
        logger.error(
            "[ORCHESTRATOR OUTPUT GUARDRAIL] Phát hiện và chặn nội dung nhạy cảm: %s",
            sanitized_res.violation_type,
        )
        return {
            "agent_output": sanitized_res.sanitized_text,
            "messages": [AIMessage(content=sanitized_res.sanitized_text or "")],
        }

    return {"agent_output": sanitized_res.sanitized_text}
