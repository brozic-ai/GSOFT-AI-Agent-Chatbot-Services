import logging
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.ai.agent.procurement.prompts.registry import get_generator_messages, get_generator_prompt
from app.ai.agent.procurement.state import ProcurementState
from app.core.user_context import get_resolved_user_name
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def responder_node(state: ProcurementState) -> Dict[str, Any]:
    """
    Stage 3: Generator / Responder Node cho Procurement Pipeline.
    - Nhận kết quả từ ToolNode (các ToolMessage chứa dữ liệu API gAMSPro).
    - Nạp prompt 'procurement_generator' từ Langfuse và compile với:
        + query (câu hỏi người dùng)
        + chat_history (lịch sử hội thoại)
        + tool_result (kết quả thực thi tool)
    - Sinh câu trả lời Markdown hoàn chỉnh, đối soát ngân sách, deep link và khuyến nghị.
    """
    messages = list(state.get("messages", [])) if isinstance(state, dict) else list(state.messages)

    # 1. Định vị HumanMessage cuối cùng (lượt chat hiện tại)
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    user_query = str(messages[last_human_idx].content) if last_human_idx != -1 else ""

    # 2. Xây dựng chat_history từ các tin nhắn trước HumanMessage cuối
    history_messages = messages[:last_human_idx] if last_human_idx > 0 else []
    chat_history = []
    for m in history_messages:
        if isinstance(m, HumanMessage):
            chat_history.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage) and m.content:
            chat_history.append({"role": "assistant", "content": str(m.content)})

    # 3. Thu thập kết quả từ tất cả ToolMessage của lượt hiện tại
    current_turn = messages[last_human_idx:] if last_human_idx != -1 else messages
    tool_messages = [m for m in current_turn if isinstance(m, ToolMessage)]

    tool_result_parts = []
    for tm in tool_messages:
        content_str = str(tm.content).strip()
        t_name = getattr(tm, "name", None) or "Tool"
        tool_result_parts.append(f"[{t_name}]:\n{content_str}")

    tool_result_str = "\n\n---\n\n".join(tool_result_parts) if tool_result_parts else "(Không có dữ liệu trả về từ công cụ)"

    # 4. Nạp và compile Chat Prompt 'procurement_generator' từ Langfuse
    prompt_messages = get_generator_messages(
        query=user_query,
        tool_result=tool_result_str,
        chat_history=chat_history,
    )

    # Đưa ngữ cảnh cán bộ đang đăng nhập vào nếu cần
    uname = state.get("user_name") or get_resolved_user_name()
    if uname and prompt_messages:
        if isinstance(prompt_messages[0], SystemMessage):
            prompt_messages[0] = SystemMessage(
                content=prompt_messages[0].content + f"\n\nLưu ý: Tên cán bộ đang đăng nhập là '{uname}'."
            )

    # 5. Thực thi LLM sinh câu trả lời Markdown cuối cùng
    try:
        llm = get_chat_model()
        response = await llm.ainvoke(prompt_messages)
        ai_content = str(response.content).strip() if response.content else ""

        if ai_content:
            return {"messages": [AIMessage(content=ai_content)]}
    except Exception as ex:
        logger.error("[PROCUREMENT-GENERATOR] Lỗi tổng hợp phản hồi từ LLM: %s", ex, exc_info=True)

    # 6. Fallback an toàn: Trả về nội dung từ ToolMessage gần nhất nếu LLM gặp sự cố
    fallback_content = ""
    for tm in reversed(tool_messages):
        if tm.content and str(tm.content).strip():
            fallback_content = str(tm.content).strip()
            break

    return {"messages": [AIMessage(content=fallback_content or "Đã hoàn tất thao tác trên hệ thống gAMSPro.")]}
