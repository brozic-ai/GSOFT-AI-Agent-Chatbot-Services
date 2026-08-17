from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.procurement.nodes.agent_node import agent_node
from app.ai.agent.procurement.state import ProcurementState
from app.ai.agent.procurement.tools import PROCUREMENT_TOOLS


def should_continue(state: ProcurementState) -> str:
    """
    Điều hướng luồng xử lý của Procurement Agent:
    - Nếu LLM sinh yêu cầu gọi tool (tool_calls) -> chuyển sang 'tools_node'.
    - Nếu LLM đã hoàn tất câu trả lời (final answer) -> kết thúc (END).
    """
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    if not messages:
        return END

    last_message = messages[-1]
    # Kiểm tra xem tin nhắn cuối cùng của AI có chứa tool_calls hay không
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools_node"

    return END


# 1. Khởi tạo StateGraph với ProcurementState
graph = StateGraph(ProcurementState)

# 2. Thêm các Node: agent_node và tools_node (ToolNode)
graph.add_node("agent_node", agent_node)
graph.add_node("tools_node", ToolNode(PROCUREMENT_TOOLS))

# 3. Đặt điểm bắt đầu (Entry Point)
graph.set_entry_point("agent_node")

# 4. Thiết lập Conditional Edge từ agent_node
graph.add_conditional_edges(
    "agent_node",
    should_continue,
    {
        "tools_node": "tools_node",
        END: END,
    },
)

# 5. Thiết lập Edge quay lại agent_node sau khi thực thi tools_node
graph.add_edge("tools_node", "agent_node")

# 6. Compile procurement_graph
procurement_graph = graph.compile()
