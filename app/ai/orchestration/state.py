"""
Orchestrator State: Định nghĩa State chung cho hệ thống Multi-Agent Orchestrator.
Sử dụng TypedDict để tương thích hoàn toàn với LangGraph và hỗ trợ truy cập dạng Dict.
"""

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.ai.agent.supervisor.schemas import RouterOutput
from app.ai.guardrails.guardrail import GuardrailResult


class OrchestratorState(TypedDict, total=False):
    """Trạng thái tổng thể luồng điều phối Multi-Agent."""

    session_id: str
    user_query: str
    user_info: Optional[Dict[str, Any]]
    chat_history: Optional[List[Dict[str, Any]]]

    # Danh sách message có reducer add_messages của LangGraph
    messages: Annotated[List[BaseMessage], add_messages]

    # Kết quả phân loại Intent từ Supervisor
    route: Optional[RouterOutput]

    # Kết quả kiểm duyệt an toàn Guardrail
    guardrail_result: Optional[GuardrailResult]

    # Kết quả đầu ra của Sub-Agent
    agent_output: Optional[str]
    rag_context: Optional[List[str]]
    error_state: Optional[str]
