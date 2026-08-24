from app.ai.agent.agentic_rag.tools.doc_metadata_tool import get_document_metadata
from app.ai.agent.agentic_rag.tools.policy_category_tool import list_policy_categories
from app.ai.agent.agentic_rag.tools.search_policy_docs_tool import (
    search_policy_and_manual_docs,
    set_rbac_context,
    vector_search_tool,
)

RAG_TOOLS = [
    search_policy_and_manual_docs,
    vector_search_tool,
    get_document_metadata,
    list_policy_categories,
]

__all__ = [
    "search_policy_and_manual_docs",
    "vector_search_tool",
    "get_document_metadata",
    "list_policy_categories",
    "set_rbac_context",
    "RAG_TOOLS",
]

