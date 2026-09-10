"""
Agent Adapters: Cầu nối điều phối giữa Orchestrator Graph và các Sub-Agent.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from app.ai.agent.fallback.nodes.fallback_node import fallback_node
from app.ai.agent.faq.graph.graph import faq_graph
from app.ai.agent.agentic_rag.prompts.registry import get_user_prompt as get_rag_user_prompt
from app.ai.agent.procurement.graph.graph import procurement_graph
from app.ai.agent.procurement.prompts.registry import get_user_prompt as get_procurement_user_prompt

logger = logging.getLogger(__name__)


def resolve_procurement_anaphora(query: str, chat_history: Optional[List[Dict[str, Any]]]) -> str:
    """
    Giải quyết tham chiếu chiếu ngữ (Anaphora Resolution) và phân trang cho câu hỏi tiếp nối:
    - 'Cho tôi xem chi tiết tờ trình đầu tiên' -> 'Cho tôi xem chi tiết tờ trình PUR/2026/000097'
    - 'Xem tờ thứ 2' -> 'Cho tôi xem chi tiết tờ trình PUR/2026/000096'
    - 'Xem tiếp trang 2' -> 'Xem tiếp trang 2 danh sách tờ trình mua sắm trên hệ thống gAMSPro'
    """
    if not chat_history:
        return query

    clean_q = (query or "").strip().lower().strip("*_\"'")

    # 1. Xử lý phân trang
    if re.search(r"^(xem\s+)?(tiếp\s+)?trang\s+(\d+)", clean_q):
        m = re.search(r"trang\s+(\d+)", clean_q)
        if m:
            page_num = m.group(1)
            return f"Xem tiếp trang {page_num} danh sách tờ trình mua sắm trên hệ thống gAMSPro."

    # 2. Xử lý tham chiếu "tờ trình này", "tờ này", "hồ sơ này", "tờ vừa rồi", "tờ đó"
    this_doc_pattern = r"(chi\s+tiết\s+)?(tờ\s+trình|hồ\s+sơ|tờ|đơn|mục|cái)\s+(này|đó|đấy|vừa\s+rồi|vừa\s+nhắc|trên)"
    if re.search(this_doc_pattern, clean_q):
        for h in reversed(chat_history):
            content = h.get("content", "")
            m = re.search(r"(PUR/\d{4}/\d{6}|TRRD\d{8,})", content, re.IGNORECASE)
            if m:
                selected_code = m.group(1).upper()
                logger.info("[ANAPHORA] Đã giải quyết anaphora '%s' thành mã gần nhất '%s'", query, selected_code)
                return f"Cho tôi xem chi tiết tờ trình {selected_code} trên hệ thống gAMSPro."

    # 3. Xử lý tham chiếu thứ tự tờ trình
    ordinal_pattern = r"(chi\s+tiết\s+)?(tờ\s+trình|hồ\s+sơ|đơn|mục|cái)\s+(đầu\s+tiên|thứ\s+\d+|thứ\s+[a-zà-ỹ]+|số\s+\d+|đầu)"
    if not re.search(ordinal_pattern, clean_q):
        return query

    # Tìm tin nhắn gần nhất của Assistant
    last_ai_content = ""
    for h in reversed(chat_history):
        if h.get("role") in ("assistant", "ai"):
            last_ai_content = h.get("content", "")
            break

    if not last_ai_content:
        return query

    # Trích xuất danh sách mã Tờ trình theo thứ tự xuất hiện (ví dụ PUR/2026/000097)
    pur_matches = []
    for m in re.finditer(r"(PUR/\d{4}/\d{6}|TRRD\d{8,})", last_ai_content, re.IGNORECASE):
        code = m.group(1).upper()
        if code not in pur_matches:
            pur_matches.append(code)

    if not pur_matches:
        return query

    # Bản đồ chỉ số thứ tự tiếng Việt
    ordinal_map = {
        "đầu tiên": 0, "thứ nhất": 0, "số 1": 0, "dòng 1": 0, "mục 1": 0, "cái đầu": 0,
        "thứ 2": 1, "thứ hai": 1, "số 2": 1, "dòng 2": 1, "mục 2": 1,
        "thứ 3": 2, "thứ ba": 2, "số 3": 2, "dòng 3": 2, "mục 3": 2,
        "thứ 4": 3, "thứ tư": 3, "số 4": 3, "dòng 4": 3, "mục 4": 3,
        "thứ 5": 4, "thứ năm": 4, "số 5": 4, "dòng 5": 4, "mục 5": 4,
        "thứ 6": 5, "thứ sáu": 5, "số 6": 5,
        "thứ 7": 6, "thứ bảy": 6, "số 7": 6,
        "thứ 8": 7, "thứ tám": 7, "số 8": 7,
        "thứ 9": 8, "thứ chín": 8, "số 9": 8,
        "thứ 10": 9, "thứ mười": 9, "số 10": 9,
    }

    target_idx = None
    for k, idx in ordinal_map.items():
        if k in clean_q:
            target_idx = idx
            break

    if target_idx is not None and target_idx < len(pur_matches):
        selected_code = pur_matches[target_idx]
        logger.info("[ANAPHORA] Đã giải quyết anaphora '%s' thành mã '%s'", query, selected_code)
        return f"Cho tôi xem chi tiết tờ trình {selected_code} trên hệ thống gAMSPro."

    return query


async def call_procurement_agent(state: Any) -> Dict[str, Any]:
    """Adapter kích hoạt Procurement Agent (gAMSPro Multi-turn Slot Filling)."""
    user_query = state.get("user_query", "") if isinstance(state, dict) else getattr(state, "user_query", "")
    chat_history = state.get("chat_history", []) if isinstance(state, dict) else getattr(state, "chat_history", [])

    # 1. Giải quyết tham chiếu anaphora / phân trang trước khi đưa vào Procurement Graph
    resolved_query = resolve_procurement_anaphora(query=user_query, chat_history=chat_history)
    logger.info("[ORCHESTRATOR -> PROCUREMENT] Điều phối: '%s' (resolved: '%s')", str(user_query)[:60], str(resolved_query)[:60])

    clean_q = (user_query or "").strip().lower().strip("*_\"'")

    try:
        # Chuẩn bị tin nhắn đầu vào cho Procurement Graph từ Langfuse Prompt
        raw_msgs = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
        messages = list(raw_msgs or [])
        if not messages:
            formatted_prompt = get_procurement_user_prompt(query=resolved_query, chat_history=chat_history)
            messages = [HumanMessage(content=formatted_prompt)]
        else:
            # Cập nhật tin nhắn Human cuối cùng với resolved_query nếu có sự thay đổi
            if resolved_query != user_query and isinstance(messages[-1], HumanMessage):
                messages[-1] = HumanMessage(content=resolved_query)

        # Chạy Procurement Sub-graph
        procurement_result = await procurement_graph.ainvoke({"messages": messages})
        res_messages = procurement_result.get("messages", [])
        
        # 1. Cô lập chỉ các tin nhắn thuộc lượt hội thoại hiện tại (Current-turn Isolation)
        # Tuyệt đối không duyệt lùi qua HumanMessage cuối cùng để tránh lấy nhầm AIMessage của các lượt cũ trong quá khứ!
        last_human_idx = -1
        for i in range(len(res_messages) - 1, -1, -1):
            if isinstance(res_messages[i], HumanMessage):
                last_human_idx = i
                break

        current_turn_messages = (
            res_messages[last_human_idx + 1:]
            if last_human_idx != -1
            else res_messages
        )

        last_ai_msg = ""
        for msg in reversed(current_turn_messages):
            if isinstance(msg, AIMessage) and msg.content and str(msg.content).strip():
                last_ai_msg = str(msg.content).strip()
                break

        # 2. Fallback: Nếu LLM ở lượt này chỉ gọi tool mà không sinh text tổng hợp (hoặc bị chạm loop guard),
        # lấy trực tiếp nội dung chi tiết từ ToolMessage gần nhất của lượt hiện tại
        from langchain_core.messages import ToolMessage
        if not last_ai_msg:
            for msg in reversed(current_turn_messages):
                if isinstance(msg, ToolMessage) and msg.content and str(msg.content).strip():
                    last_ai_msg = str(msg.content).strip()
                    break

        # 3. Bảo toàn thông tin nghiệp vụ: Nếu trong lượt có ToolMessage kết quả tra cứu quan trọng
        # (kế hoạch ngân sách, chi tiết tờ trình, đơn hàng PO, tạo tờ trình thành công...) mà last_ai_msg bị thiếu,
        # ưu tiên dùng thông tin đầy đủ từ ToolMessage
        business_keywords = (
            "THÔNG TIN KẾ HOẠCH NGÂN SÁCH LIÊN KẾT:",
            "CHI TIẾT TỜ TRÌNH:",
            "THÔNG TIN ĐƠN ĐẶT HÀNG PO:",
            "Đơn hàng PO trên gAMSPro",
            "TẠO MỚI TỜ TRÌNH MUA SẮM THÀNH CÔNG",
            "GỬI PHÊ DUYỆT TỜ TRÌNH THÀNH CÔNG",
        )
        for msg in reversed(current_turn_messages):
            if isinstance(msg, ToolMessage) and any(kw in str(msg.content) for kw in business_keywords):
                matched_kw = next(kw for kw in business_keywords if kw in str(msg.content))
                if not last_ai_msg or (len(last_ai_msg) < 50 and matched_kw not in last_ai_msg):
                    last_ai_msg = str(msg.content).strip()
                break

        # 4. Khử lặp văn bản (Trường hợp LLM nhỏ sinh lặp nguyên văn nội dung bảng biểu 2 lần liên tiếp)
        if len(last_ai_msg) > 60:
            half = len(last_ai_msg) // 2
            # So khớp 2 nửa chuỗi
            part1 = last_ai_msg[:half].strip()
            part2 = last_ai_msg[half:].strip()
            if part1 == part2:
                last_ai_msg = part1

        # 5. Lọc bỏ các thẻ XML kỹ thuật như <error>, </error>, <warning>, v.v.
        if last_ai_msg:
            last_ai_msg = re.sub(r"</?(?:error|warning|result|output|response|final_answer|call)[^>]*>", "", last_ai_msg, flags=re.IGNORECASE).strip()

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
    chat_history = (
        state.get("chat_history", [])
        if isinstance(state, dict)
        else getattr(state, "chat_history", [])
    )
    logger.info(
        "[ORCHESTRATOR -> RAG] Điều phối câu hỏi sang RAG Knowledge Agent: '%s'",
        str(user_query)[:80],
    )

    try:
        # Chuẩn bị tin nhắn đầu vào cho RAG Knowledge Graph từ Langfuse Prompt
        raw_msgs = (
            state.get("messages", [])
            if isinstance(state, dict)
            else getattr(state, "messages", [])
        )
        messages = list(raw_msgs or [])
        if not messages:
            formatted_prompt = get_rag_user_prompt(query=user_query, chat_history=chat_history)
            messages = [HumanMessage(content=formatted_prompt)]

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

        docs = rag_result.get("documents", [])
        citations = rag_result.get("citations", [])
        final_answer = rag_result.get("final_answer", "")
        res_messages = rag_result.get("messages", [])

        # Cô lập chỉ tin nhắn của lượt hiện tại
        last_human_idx = -1
        for i in range(len(res_messages) - 1, -1, -1):
            if isinstance(res_messages[i], HumanMessage):
                last_human_idx = i
                break
        current_turn_messages = res_messages[last_human_idx + 1:] if last_human_idx != -1 else res_messages

        if not final_answer:
            for msg in reversed(current_turn_messages):
                if isinstance(msg, AIMessage) and msg.content and str(msg.content).strip():
                    final_answer = str(msg.content).strip()
                    break

        # Theo sơ đồ kiến trúc: Khi RAG không tìm thấy tài liệu -> Tự động thử tra cứu FAQ
        no_doc_signals = ["không tìm thấy", "chưa tìm thấy", "không có thông tin", "chưa có tài liệu"]
        is_rag_miss = (
            (not docs and not citations)
            or (final_answer and any(kw in final_answer.lower() for kw in no_doc_signals))
        )

        if is_rag_miss:
            logger.info("[ORCHESTRATOR -> RAG] Không tìm thấy tài liệu quy chế -> Kích hoạt fallback thử tra cứu kho FAQ...")
            try:
                from app.ai.agent.faq.services.faq_retriever import retrieve_and_rerank_faqs

                faq_retrieval = await retrieve_and_rerank_faqs(query=user_query, top_k=2)
                if faq_retrieval.get("found") and faq_retrieval.get("faqs"):
                    top_faq = faq_retrieval["faqs"][0]
                    faq_msg = (
                        f"ℹ️ Tôi không tìm thấy thông tin trong tài liệu quy chế nội bộ, "
                        f"nhưng có hướng dẫn thường gặp (FAQ) liên quan sau đây:\n\n"
                        f"**{top_faq['question']}**\n\n"
                        f"{top_faq['answer']}"
                    )
                    logger.info("[ORCHESTRATOR -> RAG -> FAQ HIT] Đã tìm thấy FAQ bổ trợ cho câu hỏi của người dùng.")
                    return {
                        "agent_output": faq_msg,
                        "final_answer": faq_msg,
                        "rag_context": [],
                        "citations": faq_retrieval.get("citations", []),
                        "messages": [AIMessage(content=faq_msg)],
                    }
            except Exception as faq_fallback_err:
                logger.warning("[ORCHESTRATOR -> RAG -> FAQ ERROR] Lỗi khi tra cứu fallback FAQ: %s", faq_fallback_err)

        if not final_answer:
            final_answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."

        return {
            "agent_output": final_answer,
            "final_answer": final_answer,
            "rag_context": docs,
            "citations": citations,
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
    """Adapter kích hoạt FAQ Agent (Sub-graph ReAct: Tra cứu cơ sở tri thức câu hỏi thường gặp)."""
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    logger.info("[ORCHESTRATOR -> FAQ] Điều phối sang FAQ Agent: '%s'", str(user_query)[:80])

    try:
        raw_msgs = (
            state.get("messages", [])
            if isinstance(state, dict)
            else getattr(state, "messages", [])
        )
        messages_list = list(raw_msgs or [])
        if not messages_list and user_query:
            messages_list = [HumanMessage(content=user_query)]

        faq_input = {
            "messages": messages_list,
            "user_query": user_query,
            "session_id": str(state.get("session_id", "orchestrator-faq-session")),
        }
        faq_result = await faq_graph.ainvoke(faq_input)
        res_messages = faq_result.get("messages", [])
        final_answer = faq_result.get("final_answer", "")

        # Cô lập chỉ tin nhắn của lượt hiện tại
        last_human_idx = -1
        for i in range(len(res_messages) - 1, -1, -1):
            if isinstance(res_messages[i], HumanMessage):
                last_human_idx = i
                break
        current_turn_messages = res_messages[last_human_idx + 1:] if last_human_idx != -1 else res_messages

        last_ai_msg = final_answer
        if not last_ai_msg:
            for msg in reversed(current_turn_messages):
                if isinstance(msg, AIMessage) and msg.content and str(msg.content).strip():
                    last_ai_msg = str(msg.content).strip()
                    break

        if not last_ai_msg:
            from langchain_core.messages import ToolMessage
            for msg in reversed(current_turn_messages):
                if isinstance(msg, ToolMessage) and msg.content and str(msg.content).strip():
                    last_ai_msg = str(msg.content).strip()
                    break

        if not last_ai_msg:
            last_ai_msg = "Tôi chưa tìm thấy câu trả lời phù hợp trong danh mục câu hỏi thường gặp (FAQ)."

        citations = faq_result.get("citations", [])

        return {
            "agent_output": last_ai_msg,
            "final_answer": last_ai_msg,
            "citations": citations,
            "retrieved_faqs": faq_result.get("retrieved_faqs", []),
            "messages": res_messages,
        }

    except Exception as ex:
        logger.error(
            "[ORCHESTRATOR -> FAQ ERROR] Lỗi khi gọi FAQ Graph: %s",
            ex,
            exc_info=True,
        )
        err_msg = (
            "⚠️ Hệ thống tra cứu câu hỏi thường gặp (FAQ) hiện đang gặp sự cố kết nối. "
            "Bạn vui lòng thử lại sau ít phút hoặc liên hệ quản trị viên."
        )
        return {
            "agent_output": err_msg,
            "final_answer": err_msg,
            "messages": [AIMessage(content=err_msg)],
            "error_state": str(ex),
        }


async def call_fallback_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter kích hoạt Fallback Agent (Chào hỏi / Hướng dẫn / Ngoài phạm vi)."""
    logger.info("[ORCHESTRATOR -> FALLBACK] Điều phối sang Fallback Agent...")
    return await fallback_node(state)
