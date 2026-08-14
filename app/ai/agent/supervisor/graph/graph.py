from langgraph.graph import END, StateGraph

from app.ai.agent.supervisor.nodes.classify import classify_intent_node
from app.ai.agent.supervisor.state import SupervisorState

graph = StateGraph(SupervisorState)
graph.add_node("classify_intent", classify_intent_node)
graph.set_entry_point("classify_intent")
graph.add_edge("classify_intent", END)

supervisor_graph = graph.compile()
