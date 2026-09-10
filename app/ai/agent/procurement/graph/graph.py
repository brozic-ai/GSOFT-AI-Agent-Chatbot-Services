import logging
from typing import Any
from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.procurement.nodes.responder_node import responder_node
from app.ai.agent.procurement.nodes.router_node import router_node
from app.ai.agent.procurement.state import ProcurementState
from app.ai.agent.procurement.tools import PROCUREMENT_TOOLS

logger = logging.getLogger(__name__)


def should_continue_router(state: ProcurementState) -> str:
    """
    Điều hướng luồng xử lý từ Router Node:
    - Nếu Router sinh tool_calls (type: tool_call) -> chuyển sang 'tools_node' để thực thi.
    - Nếu Router trả về need_info hoặc phản hồi giao tiếp trực tiếp -> kết thúc turn (END).
    """
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info(
            "[PROCUREMENT-GRAPH] Phát hiện %d tool call(s) từ Router Node. Chuyển sang 'tools_node'.",
            len(last_message.tool_calls),
        )
        return "tools_node"

    return END


# Alias để tương thích ngược với các module import should_continue
should_continue = should_continue_router

# =========================================================================
# KHỞI TẠO STATEGRAPH - KIẾN TRÚC 2-STAGE PIPELINE
# =========================================================================
# Stage 1: router_node -> Nạp prompt Langfuse, phân tích output contract JSON
# Stage 2: tools_node -> Thực thi các Tool gAMSPro kết nối C# Backend
# Stage 3: responder_node -> Tổng hợp kết quả, bảng biểu Markdown & deep link
# =========================================================================

graph = StateGraph(ProcurementState)

# 1. Thêm các Node vào Pipeline
graph.add_node("router_node", router_node)
graph.add_node("tools_node", ToolNode(PROCUREMENT_TOOLS))
graph.add_node("responder_node", responder_node)

# 2. Đặt điểm bắt đầu (Entry Point) là Router Node
graph.set_entry_point("router_node")

# 3. Thiết lập Conditional Edge từ router_node
graph.add_conditional_edges(
    "router_node",
    should_continue_router,
    {
        "tools_node": "tools_node",
        END: END,
    },
)

# 4. Sau khi ToolNode chạy xong, chuyển thẳng sang responder_node để tổng hợp
graph.add_edge("tools_node", "responder_node")

# 5. Responder Node hoàn tất câu trả lời gửi về cho người dùng
graph.add_edge("responder_node", END)

# 6. Compile procurement_graph
procurement_graph = graph.compile()
