"""
Orchestrator State: Định nghĩa State chung cho hệ thống Multi-Agent Orchestrator.
Sử dụng TypedDict để tương thích hoàn toàn với LangGraph và hỗ trợ truy cập dạng Dict.
"""

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.ai.agent.supervisor.schemas import RouterOutput
from app.ai.guardrails.guardrail import GuardrailResult


class OrchestratorState(TypedDict, total=False):
    """Trạng thái tổng thể luồng điều phối Multi-Agent."""

    session_id: str
    user_query: str
    user_info: dict[str, Any] | None
    chat_history: list[dict[str, Any]] | None
    model_level: str | None
    routing_metadata: dict[str, Any] | None

    # Danh sách message có reducer add_messages của LangGraph
    messages: Annotated[list[BaseMessage], add_messages]

    # Kết quả phân loại Intent từ Supervisor
    route: RouterOutput | None
    intent: str | None

    # Kết quả kiểm duyệt an toàn Guardrail
    guardrail_result: GuardrailResult | None

    # Cờ đánh dấu đã match FAQ siêu tốc (Zero-LLM Fast-Path)
    faq_fast_match: bool | None

    # Kết quả đầu ra của Sub-Agent
    agent_output: str | None
    rag_context: list[str] | None
    citations: list[dict[str, Any]] | None
    error_state: str | None
