"""
FAQ Agent Graph — Đồ thị trạng thái tối ưu cho FAQ Agent.

Kiến trúc Direct Pipeline (Retrieve -> Rerank -> Generate / Fallback):
  ┌───────────────────────┐
  │   retrieve_faq_node   │ (Hybrid Search + Multilingual Cross-Encoder Rerank)
  └──────────┬────────────┘
             │
      ┌──────┴──────┐
      │ có FAQ?     │ không có FAQ?
      ▼             ▼
┌──────────────┐ ┌───────────────┐
│generate_node │ │ fallback_node │ (Zero LLM latency, trả kết quả tức thì)
└──────┬───────┘ └───────┬───────┘
       ▼                 ▼
      END               END

Giảm từ 2 lượt LLM ReAct (3-4s) xuống 1 lượt LLM duy nhất (< 1s) hoặc 0 lượt nếu fallback!
Không còn nguy cơ LLM quên gọi tool hoặc hallucination.
"""

from langgraph.graph import END, StateGraph

from app.ai.agent.faq.nodes.faq_node import (
    fallback_faq_node,
    generate_faq_node,
    retrieve_faq_node,
)
from app.ai.agent.faq.state import FAQState


def _route_after_retrieval(state: FAQState) -> str:
    """Điều hướng sau `retrieve_faq_node`:
    - Nếu tìm thấy FAQ phù hợp -> chuyển sang 'generate_faq_node' để LLM tổng hợp lời đáp.
    - Nếu không tìm thấy FAQ nào -> chuyển thẳng sang 'fallback_faq_node' để trả lời lịch sự.
    """
    faqs = state.get("retrieved_faqs", [])
    if faqs:
        return "generate_faq_node"
    return "fallback_faq_node"


# ── 1. Khởi tạo StateGraph ──
_graph = StateGraph(FAQState)

# ── 2. Đăng ký các Nodes ──
_graph.add_node("retrieve_faq_node", retrieve_faq_node)
_graph.add_node("generate_faq_node", generate_faq_node)
_graph.add_node("fallback_faq_node", fallback_faq_node)

# ── 3. Entry Point ──
_graph.set_entry_point("retrieve_faq_node")

# ── 4. Cạnh điều kiện sau retrieve_faq_node ──
_graph.add_conditional_edges(
    "retrieve_faq_node",
    _route_after_retrieval,
    {
        "generate_faq_node": "generate_faq_node",
        "fallback_faq_node": "fallback_faq_node",
    },
)

# ── 5. Kết thúc sau generate hoặc fallback ──
_graph.add_edge("generate_faq_node", END)
_graph.add_edge("fallback_faq_node", END)

# ── 6. Compile ──
faq_graph = _graph.compile()

__all__ = ["faq_graph"]
