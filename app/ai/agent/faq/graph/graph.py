"""
FAQ Agent Graph — Đồ thị trạng thái độc lập cho FAQ Agent.

Kiến trúc ReAct (Reason + Act) 2 node:
  ┌──────────────────┐
  │  faq_agent_node  │ ←─────────────────┐
  └────────┬─────────┘                   │
           │ tool_calls?                 │
     ┌─────┴──────┐                      │
     │ (có tool)  │ (không tool)         │
     ▼            ▼                      │
 tools_node    END                       │
     │                                   │
     └───────────────────────────────────┘
           (tool result → quay lại agent)

Export `faq_graph` để Supervisor chính gọi trực tiếp khi intent = 'faq'.
"""

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.faq.nodes.faq_node import faq_agent_node
from app.ai.agent.faq.state import FAQState
from app.ai.agent.faq.tools import FAQ_TOOLS


def _should_continue(state: FAQState) -> str:
    """Điều hướng sau `faq_agent_node`:

    - Nếu LLM sinh tool_calls → chuyển sang 'tools_node' để thực thi tìm kiếm.
    - Nếu không có tool_calls → LLM đã tổng hợp xong câu trả lời → kết thúc tại END.
    """
    messages = (
        list(state.get("messages", []))
        if isinstance(state, dict)
        else list(state.messages)
    )
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools_node"

    return END


# ── 1. Khởi tạo StateGraph ──
_graph = StateGraph(FAQState)

# ── 2. Đăng ký các Nodes ──
_graph.add_node("faq_agent_node", faq_agent_node)
_graph.add_node("tools_node", ToolNode(FAQ_TOOLS))

# ── 3. Entry Point ──
_graph.set_entry_point("faq_agent_node")

# ── 4. Cạnh điều kiện: Sau faq_agent_node ──
_graph.add_conditional_edges(
    "faq_agent_node",
    _should_continue,
    {
        "tools_node": "tools_node",
        END: END,
    },
)

# ── 5. Sau khi tool chạy xong → quay lại faq_agent_node để tổng hợp câu trả lời ──
_graph.add_edge("tools_node", "faq_agent_node")

# ── 6. Compile ──
faq_graph = _graph.compile()

__all__ = ["faq_graph"]
