from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.agentic_rag.nodes.agent_node import rag_agent_node
from app.ai.agent.agentic_rag.nodes.generator_node import generator_node
from app.ai.agent.agentic_rag.nodes.grader_node import grader_node
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.ai.agent.agentic_rag.tools import RAG_TOOLS

MAX_RETRIES = 2


# ── Conditional Routing Functions ──


def should_retrieve_or_answer(state: AgenticRagState) -> str:
    """Điều hướng sau `rag_agent_node`:

    - Nếu LLM sinh yêu cầu gọi tool (`tool_calls`) -> chuyển sang 'tools_node'.
    - Nếu không có `tool_calls` (chitchat/đã đủ thông tin) -> chuyển sang 'generator_node'.
    """
    messages = (
        state.get("messages", [])
        if isinstance(state, dict)
        else getattr(state, "messages", [])
    )
    if not messages:
        return "generator_node"

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools_node"

    return "generator_node"


def should_generate_or_retry(state: AgenticRagState) -> str:
    """Điều hướng sau `grader_node`:

    - Nếu tài liệu liên quan (`is_relevant = True`) HOẶC đã đạt giới hạn thử lại (`retry_count >= MAX_RETRIES`)
      -> chuyển sang 'generator_node'.
    - Nếu tài liệu không liên quan (`is_relevant = False`) VÀ còn lượt thử lại
      -> loop quay lại 'rag_agent_node' để tìm kiếm lại.
    """
    is_relevant = (
        state.get("is_relevant", False)
        if isinstance(state, dict)
        else getattr(state, "is_relevant", False)
    )
    retry_count = (
        state.get("retry_count", 0)
        if isinstance(state, dict)
        else getattr(state, "retry_count", 0)
    )

    if is_relevant or retry_count >= MAX_RETRIES:
        return "generator_node"
    return "rag_agent_node"


# ── 1. Khởi tạo StateGraph (4 Nodes) ──
graph = StateGraph(AgenticRagState)

# ── 2. Đăng ký các Nodes ──
graph.add_node("rag_agent_node", rag_agent_node)  # Node 1: Agent
graph.add_node("tools_node", ToolNode(RAG_TOOLS))  # Node 2: Tool
graph.add_node("grader_node", grader_node)  # Node 3: Document Grader
graph.add_node("generator_node", generator_node)  # Node 4: Generator

# ── 3. Thiết lập Điểm bắt đầu (Entry Point) ──
graph.set_entry_point("rag_agent_node")

# ── 4. Thiết lập các liên kết Edges & Conditional Edges ──
# 4a. Từ rag_agent_node: Cần tra cứu -> tools_node, Đã đủ thông tin -> generator_node
graph.add_conditional_edges(
    "rag_agent_node",
    should_retrieve_or_answer,
    {
        "tools_node": "tools_node",
        "generator_node": "generator_node",
    },
)

# 4b. Từ tools_node: Sau khi chạy tool -> luôn chuyển sang grader_node để chấm điểm
graph.add_edge("tools_node", "grader_node")

# 4c. Từ grader_node: Tài liệu liên quan -> generator_node, Tài liệu không liên quan -> loop back rag_agent_node
graph.add_conditional_edges(
    "grader_node",
    should_generate_or_retry,
    {
        "generator_node": "generator_node",
        "rag_agent_node": "rag_agent_node",
    },
)

# 4d. Từ generator_node: Kết thúc phiên xử lý
graph.add_edge("generator_node", END)

# ── 5. Compile Sub-graph ──
agentic_rag_graph = graph.compile()
rag_agent_graph = agentic_rag_graph

