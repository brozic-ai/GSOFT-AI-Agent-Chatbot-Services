"""
RAG Agent Graph: Fast Pipeline Architecture (1 LLM call).
Thay thế kiến trúc 4-node ReAct lãng phí latency bằng quy trình tinh gọn:
  [retrieve_rag_node] (Hybrid FTS + Vector + BGE Cross-Encoder)
         │
         ├── (Có tài liệu liên quan) ──> [generator_node] (Inline Citations + Footnotes) ──> END
         └── (Không có tài liệu)    ──> [fallback_node]  (Thông báo Zero-Hallucination) ──> END

Độ trễ giảm từ ~10-15s xuống 2-3s với độ chính xác cao hơn nhờ Cross-Encoder.
"""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.ai.agent.agentic_rag.nodes.generator_node import generator_node
from app.ai.agent.agentic_rag.nodes.retrieve_node import retrieve_rag_node
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.ai.agent.fallback.nodes.fallback_node import fallback_node


def should_generate_or_fallback(state: AgenticRagState) -> str:
    """Điều hướng sau bước Retrieve & Rerank."""
    documents = (
        state.get("documents", [])
        if isinstance(state, dict)
        else getattr(state, "documents", [])
    )
    if documents and len(documents) > 0:
        return "generator_node"
    return "fallback_node"


def should_retrieve_or_answer(state: AgenticRagState) -> str:
    """Legacy routing function for backward compatibility."""
    return should_generate_or_fallback(state)


def should_generate_or_retry(state: AgenticRagState) -> str:
    """Legacy routing function for backward compatibility."""
    return should_generate_or_fallback(state)


# ── 1. Khởi tạo StateGraph (Fast Pipeline) ──
graph = StateGraph(AgenticRagState)

# ── 2. Đăng ký các Nodes ──
graph.add_node("retrieve_rag_node", retrieve_rag_node)
graph.add_node("generator_node", generator_node)
graph.add_node("fallback_node", fallback_node)

# ── 3. Thiết lập Điểm bắt đầu (Entry Point) ──
graph.set_entry_point("retrieve_rag_node")

# ── 4. Thiết lập Edges ──
graph.add_conditional_edges(
    "retrieve_rag_node",
    should_generate_or_fallback,
    {
        "generator_node": "generator_node",
        "fallback_node": "fallback_node",
    },
)
graph.add_edge("generator_node", END)
graph.add_edge("fallback_node", END)

# ── 5. Compile Sub-graph ──
agentic_rag_graph = graph.compile()
rag_agent_graph = agentic_rag_graph

