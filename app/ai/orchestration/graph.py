"""
Orchestrator Graph: Đồ thị điều phối trung tâm toàn bộ hệ thống Multi-Agent BVBank & gAMSPro.

Luồng thực thi:
input_guardrail -> (nếu an toàn) -> classify_intent -> [procurement_agent, rag_agent, faq_agent, fallback_agent] -> output_guardrail -> END.
"""

from langgraph.graph import END, StateGraph

from app.ai.agent.supervisor.nodes.classify import classify_intent_node
from app.ai.orchestration.nodes.agent_adapters import (
    call_fallback_agent,
    call_faq_agent,
    call_procurement_agent,
    call_rag_agent,
)
from app.ai.orchestration.nodes.faq_fast_lookup_node import faq_fast_lookup_node
from app.ai.orchestration.nodes.input_guardrail_node import input_guardrail_node
from app.ai.orchestration.nodes.output_guardrail_node import output_guardrail_node
from app.ai.orchestration.router import (
    route_after_classification,
    route_after_faq_fast_lookup,
    route_after_input_guardrail,
)
from app.ai.orchestration.state import OrchestratorState

# 1. Khởi tạo StateGraph với OrchestratorState
graph = StateGraph(OrchestratorState)

# 2. Thêm các Nodes bảo vệ, Fast-Path tra cứu, phân loại và các Sub-Agent
graph.add_node("input_guardrail", input_guardrail_node)
graph.add_node("faq_fast_lookup", faq_fast_lookup_node)
graph.add_node("classify_intent", classify_intent_node)
graph.add_node("procurement_agent", call_procurement_agent)
graph.add_node("rag_agent", call_rag_agent)
graph.add_node("faq_agent", call_faq_agent)
graph.add_node("fallback_agent", call_fallback_agent)
graph.add_node("output_guardrail", output_guardrail_node)

# 3. Đặt điểm bắt đầu (Entry Point) tại Input Guardrail
graph.set_entry_point("input_guardrail")

# 4. Thiết lập Conditional Edge từ Input Guardrail
graph.add_conditional_edges(
    "input_guardrail",
    route_after_input_guardrail,
    {
        "faq_fast_lookup": "faq_fast_lookup",
        "output_guardrail": "output_guardrail",
    },
)

# 5. Thiết lập Conditional Edge từ FAQ Fast-Lookup (Zero-LLM Latency)
graph.add_conditional_edges(
    "faq_fast_lookup",
    route_after_faq_fast_lookup,
    {
        "output_guardrail": "output_guardrail",
        "classify_intent": "classify_intent",
    },
)

# 5. Thiết lập Conditional Edge từ Classify Intent sang các Agent
graph.add_conditional_edges(
    "classify_intent",
    route_after_classification,
    {
        "procurement_agent": "procurement_agent",
        "rag_agent": "rag_agent",
        "faq_agent": "faq_agent",
        "fallback_agent": "fallback_agent",
    },
)

# 6. Các Sub-Agents xử lý xong đều đổ về Output Guardrail để kiểm duyệt
graph.add_edge("procurement_agent", "output_guardrail")
graph.add_edge("rag_agent", "output_guardrail")
graph.add_edge("faq_agent", "output_guardrail")
graph.add_edge("fallback_agent", "output_guardrail")

# 7. Output Guardrail kiểm duyệt xong -> Kết thúc (END)
graph.add_edge("output_guardrail", END)

# 8. Compile Orchestrator Graph
orchestrator_graph = graph.compile()
