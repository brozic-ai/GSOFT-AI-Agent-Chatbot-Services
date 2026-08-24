"""
Agent Adapters: Cầu nối điều phối giữa Orchestrator Graph và các Sub-Agent.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage

from app.ai.agent.fallback.nodes.fallback_node import fallback_node
from app.ai.agent.faq.nodes.faq_node import faq_node
from app.ai.agent.agentic_rag.nodes.rag_node import rag_node
from app.ai.agent.procurement.graph.graph import procurement_graph

logger = logging.getLogger(__name__)


async def call_procurement_agent(state: Any) -> Dict[str, Any]:
    """Adapter kích hoạt Procurement Agent (gAMSPro Multi-turn Slot Filling)."""
    user_query = state.get("user_query", "") if isinstance(state, dict) else getattr(state, "user_query", "")
    logger.info("[ORCHESTRATOR -> PROCUREMENT] Điều phối câu hỏi: '%s'", str(user_query)[:80])

    try:
        # Chuẩn bị tin nhắn đầu vào cho Procurement Graph
        raw_msgs = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
        messages = list(raw_msgs or [])
        if not messages:
            messages = [HumanMessage(content=user_query)]

        # Chạy Procurement Sub-graph
        procurement_result = await procurement_graph.ainvoke({"messages": messages})
        res_messages = procurement_result.get("messages", [])
        
        last_ai_msg = ""
        for msg in reversed(res_messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_ai_msg = str(msg.content)
                break

        # Fallback: Nếu LLM không sinh text tổng hợp, lấy trực tiếp nội dung từ ToolMessage
        if not last_ai_msg:
            from langchain_core.messages import ToolMessage
            for msg in reversed(res_messages):
                if isinstance(msg, ToolMessage) and msg.content:
                    last_ai_msg = str(msg.content)
                    break

        if not last_ai_msg:
            last_ai_msg = "Tôi đã xử lý yêu cầu nghiệp vụ mua sắm của bạn trên hệ thống gAMSPro."

        return {
            "agent_output": last_ai_msg,
            "messages": res_messages,
        }

    except Exception as ex:
        logger.error("[ORCHESTRATOR -> PROCUREMENT ERROR] Lỗi khi gọi Procurement Graph: %s", ex, exc_info=True)
        err_msg = (
            "⚠️ Hệ thống gAMSPro hiện đang gặp sự cố kết nối hoặc phản hồi chậm. "
            "Bạn vui lòng thử lại sau ít phút hoặc thao tác trực tiếp trên portal gAMSPro."
        )
        return {
            "agent_output": err_msg,
            "messages": [AIMessage(content=err_msg)],
            "error_state": str(ex),
        }


async def call_rag_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter kích hoạt RAG Knowledge Agent (Sub-graph Node: Tra cứu quy trình, quy chế, sổ tay HDSD)."""
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    logger.info(
        "[ORCHESTRATOR -> RAG] Điều phối câu hỏi sang RAG Knowledge Agent: '%s'",
        str(user_query)[:80],
    )

    try:
        # Chuẩn bị tin nhắn đầu vào cho RAG Knowledge Graph
        raw_msgs = (
            state.get("messages", [])
            if isinstance(state, dict)
            else getattr(state, "messages", [])
        )
        messages = list(raw_msgs or [])
        if not messages:
            messages = [HumanMessage(content=user_query)]

        user_info = (
            state.get("user_info", {})
            if isinstance(state, dict)
            else getattr(state, "user_info", {})
        )
        user_roles = state.get("user_roles") or (
            user_info.get("roles") if isinstance(user_info, dict) else None
        )
        user_department = state.get("user_department") or (
            user_info.get("department") if isinstance(user_info, dict) else None
        )
        session_id = state.get("session_id", "orchestrator-rag-session")

        # Thiết lập context RBAC cho các tool tra cứu văn bản
        from app.ai.agent.agentic_rag.tools.search_policy_docs_tool import (
            set_rbac_context,
        )

        set_rbac_context(
            user_roles=user_roles, user_department=user_department
        )

        rag_input = {
            "messages": messages,
            "user_query": user_query,
            "session_id": str(session_id),
            "user_roles": user_roles,
            "user_department": user_department,
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "retry_count": 0,
            "final_answer": "",
        }

        from app.ai.agent.agentic_rag.graph.graph import agentic_rag_graph

        rag_result = await agentic_rag_graph.ainvoke(rag_input)

        final_answer = rag_result.get("final_answer", "")
        res_messages = rag_result.get("messages", [])

        if not final_answer:
            for msg in reversed(res_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    final_answer = str(msg.content)
                    break

        if not final_answer:
            final_answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."

        return {
            "agent_output": final_answer,
            "final_answer": final_answer,
            "rag_context": rag_result.get("documents", []),
            "citations": rag_result.get("citations", []),
            "messages": res_messages,
        }

    except Exception as ex:
        logger.error(
            "[ORCHESTRATOR -> RAG ERROR] Lỗi khi gọi RAG Sub-graph: %s",
            ex,
            exc_info=True,
        )
        err_msg = (
            "⚠️ Hệ thống tra cứu tài liệu quy chế BVBank hiện đang gặp sự cố kết nối. "
            "Bạn vui lòng thử lại sau ít phút hoặc liên hệ quản trị viên."
        )
        return {
            "agent_output": err_msg,
            "final_answer": err_msg,
            "messages": [AIMessage(content=err_msg)],
            "error_state": str(ex),
        }



async def call_faq_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter kích hoạt FAQ Agent (Giải đáp câu hỏi thường gặp)."""
    logger.info("[ORCHESTRATOR -> FAQ] Điều phối sang FAQ Agent...")
    return await faq_node(state)


async def call_fallback_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter kích hoạt Fallback Agent (Chào hỏi / Hướng dẫn / Ngoài phạm vi)."""
    logger.info("[ORCHESTRATOR -> FALLBACK] Điều phối sang Fallback Agent...")
    return await fallback_node(state)
