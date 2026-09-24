"""FAQ Agent Module."""
from app.ai.agent.faq.graph.graph import faq_graph
from app.ai.agent.faq.nodes.faq_node import faq_agent_node
from app.ai.agent.faq.state import FAQState

# Alias tương thích với Supervisor hiện tại
faq_node = faq_agent_node

__all__ = ["faq_graph", "faq_agent_node", "faq_node", "FAQState"]
