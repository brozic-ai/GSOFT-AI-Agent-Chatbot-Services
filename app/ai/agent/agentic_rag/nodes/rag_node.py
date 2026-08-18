"""
Agentic RAG Node: Tra cứu tài liệu quy trình, quy chế ngân hàng và chính sách nội bộ.
(Stub Interface chuẩn kết nối với Orchestrator & Vector Retriever)
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


async def rag_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Node xử lý tra cứu tài liệu nghiệp vụ (RAG).
    Tích hợp kiểm tra ngữ cảnh và cơ chế Smart Escalation sang FAQ nếu không tìm thấy tài liệu.
    """
    user_query = state.get("user_query", "")
    user_info = state.get("user_info", {})
    user_roles = user_info.get("roles") if isinstance(user_info, dict) else None
    user_dep = user_info.get("department") if isinstance(user_info, dict) else None

    logger.info("[RAG AGENT] Đang tra cứu tài liệu cho câu hỏi: '%s'", user_query[:80])

    try:
        from app.routers.dependencies import get_vector_retriever
        retriever = get_vector_retriever()
        results = await retriever.retrieve_context(
            query=user_query,
            top_k=3,
            user_roles=user_roles,
            user_department=user_dep,
        )
        docs = results.get("documents", [[]])[0]
        citations = results.get("citations", [[]])[0]

        if not docs:
            logger.info("[RAG AGENT] Không tìm thấy tài liệu trong Vector DB. Smart Escalation sang FAQ/Fallback.")
            fallback_msg = (
                "Tôi không tìm thấy tài liệu quy định cụ thể nào trong hệ thống khớp với câu hỏi của bạn. "
                "Bạn vui lòng liên hệ bộ phận nghiệp vụ hoặc tham khảo mục Câu hỏi thường gặp (FAQ) nhé."
            )
            return {
                "rag_context": [],
                "agent_output": fallback_msg,
                "messages": [AIMessage(content=fallback_msg)],
            }

        # Tạo phản hồi mẫu từ các đoạn trích dẫn tìm được
        doc_names = list(set(c.get("document_name", "Tài liệu nội bộ") for c in citations if isinstance(c, dict)))
        docs_summary = "\n\n".join(docs[:2])
        response_content = (
            f"Dựa trên các tài liệu nội bộ ({', '.join(doc_names)}):\n\n"
            f"{docs_summary}\n\n"
            f"(Trích dẫn từ hệ thống quản lý tài liệu BVBank)."
        )

        return {
            "rag_context": docs,
            "agent_output": response_content,
            "messages": [AIMessage(content=response_content)],
        }

    except Exception as ex:
        logger.warning("[RAG AGENT] Lỗi khi truy vấn Vector Retriever: %s", ex)
        default_msg = f"Dựa trên tài liệu quy chế BVBank liên quan đến '{user_query}': Vui lòng kiểm tra lại quy trình hiện hành."
        return {
            "rag_context": [],
            "agent_output": default_msg,
            "messages": [AIMessage(content=default_msg)],
        }
