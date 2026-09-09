import logging
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.procurement.nodes.agent_node import procurement_node
from app.ai.agent.procurement.state import ProcurementState
from app.ai.agent.procurement.tools import PROCUREMENT_TOOLS

logger = logging.getLogger(__name__)

MAX_PROCUREMENT_TOOL_CALLS = 2


def should_continue(state: ProcurementState) -> str:
    """
    Điều hướng luồng xử lý của Procurement Agent:
    - Nếu LLM sinh yêu cầu gọi tool (tool_calls) -> chuyển sang 'tools_node'.
    - GUARD 1: Giới hạn tối đa MAX_PROCUREMENT_TOOL_CALLS (2 lần) gọi tool trong 1 lượt chat để triệt tiêu nguy cơ vòng lặp vô tận.
    - GUARD 2: Phát hiện gọi trùng lặp (Duplicate Tool Calls) cùng tool và cùng đối số -> ngắt ngay lập tức.
    - Nếu LLM đã hoàn tất câu trả lời (final answer) hoặc chạm guard -> kết thúc (END).
    """
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    if not messages:
        return END

    last_message = messages[-1]
    if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
        return END

    # 1. Đếm số lượng ToolMessage đã thực thi từ tin nhắn Human gần nhất
    executed_tool_count = 0
    executed_calls = []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage):
            executed_tool_count += 1
        if hasattr(msg, "tool_calls") and msg.tool_calls and msg is not last_message:
            for tc in msg.tool_calls:
                executed_calls.append((tc.get("name"), str(tc.get("args"))))

    # 2. Guard: Vượt quá số lần gọi tool cho phép trong 1 turn
    if executed_tool_count >= MAX_PROCUREMENT_TOOL_CALLS:
        logger.warning(
            "[PROCUREMENT-GUARD] Đã gọi tool %d lần (ngưỡng tối đa: %d). Ngắt vòng lặp ReAct để trả về phản hồi cho người dùng.",
            executed_tool_count,
            MAX_PROCUREMENT_TOOL_CALLS,
        )
        return END

    # 3. Guard: Phát hiện gọi lại tool giống hệt đối số của lần trước
    for new_tc in last_message.tool_calls:
        sig = (new_tc.get("name"), str(new_tc.get("args")))
        if sig in executed_calls:
            logger.warning(
                "[PROCUREMENT-GUARD] Phát hiện gọi lặp lại tool '%s' với đối số %s. Ngắt vòng lặp ngay lập tức.",
                sig[0],
                sig[1],
            )
            return END

    return "tools_node"


# 1. Khởi tạo StateGraph với ProcurementState
graph = StateGraph(ProcurementState)

# 2. Thêm các Node: procurement_node và tools_node (ToolNode)
graph.add_node("procurement_node", procurement_node)
graph.add_node("tools_node", ToolNode(PROCUREMENT_TOOLS))

# 3. Đặt điểm bắt đầu (Entry Point)
graph.set_entry_point("procurement_node")

# 4. Thiết lập Conditional Edge từ procurement_node
graph.add_conditional_edges(
    "procurement_node",
    should_continue,
    {
        "tools_node": "tools_node",
        END: END,
    },
)

# 5. Thiết lập Edge quay lại procurement_node sau khi thực thi tools_node
graph.add_edge("tools_node", "procurement_node")

# 6. Compile procurement_graph
procurement_graph = graph.compile()
