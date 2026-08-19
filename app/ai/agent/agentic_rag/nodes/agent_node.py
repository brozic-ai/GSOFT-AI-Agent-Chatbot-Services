import logging
from langchain_core.messages import BaseMessage, SystemMessage

from app.ai.agent.agentic_rag.prompts.registry import get_system_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.ai.agent.agentic_rag.tools import RAG_TOOLS
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def rag_agent_node(
    state: AgenticRagState,
) -> dict[str, list[BaseMessage]]:
    """Node 1: Agent chính — LLM nhận diện xem có cần tra cứu không.

    - Nếu cần tra cứu -> sinh tool_calls.
    - Nếu đã đủ thông tin -> sinh câu trả lời trực tiếp.
    - Khi loop lại (sau khi grader_node báo không liên quan), Agent tự nhận diện ngữ cảnh và thử lại với từ khóa khác.
    """
    messages = (
        list(state.get("messages", []))
        if isinstance(state, dict)
        else list(state.messages)
    )

    # 1. Đưa System Prompt vào đầu danh sách messages nếu chưa có
    if not messages or not isinstance(messages[0], SystemMessage):
        system_prompt = get_system_prompt()
        messages = [SystemMessage(content=system_prompt)] + messages

    # 2. Khởi tạo LLM và bind danh sách RAG_TOOLS
    llm = get_chat_model().bind_tools(RAG_TOOLS)

    # 3. Thực thi suy luận LLM
    response = await llm.ainvoke(messages)

    # 4. Trả về message mới để StateGraph cập nhật vào messages qua add_messages reducer
    return {"messages": [response]}


# Alias tương thích
agent_node = rag_agent_node
