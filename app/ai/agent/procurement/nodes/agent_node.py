import logging
from langchain_core.messages import BaseMessage, SystemMessage

from app.ai.agent.procurement.prompts.registry import get_system_prompt
from app.ai.agent.procurement.state import ProcurementState
from app.ai.agent.procurement.tools import PROCUREMENT_TOOLS
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def procurement_node(state: ProcurementState) -> dict[str, list[BaseMessage]]:
    """
    Node Procurement thực thi suy luận LLM cho Procurement Assistant (gAMSPro).
    - Khởi tạo LLM qua get_chat_model() liên kết với PROCUREMENT_TOOLS.
    - Đưa System Prompt vào đầu danh sách message nếu chưa có.
    - Thực thi suy luận LLM và sinh tool calls hoặc final answer.
    """
    messages = list(state.get("messages", [])) if isinstance(state, dict) else list(state.messages)

    # 1. Đưa System Prompt vào đầu danh sách messages nếu chưa có
    if not messages or not isinstance(messages[0], SystemMessage):
        system_prompt = get_system_prompt()
        messages = [SystemMessage(content=system_prompt)] + messages

    # 2. Khởi tạo LLM và bind các công cụ tra cứu gAMSPro
    llm = get_chat_model().bind_tools(PROCUREMENT_TOOLS)

    # 3. Thực thi suy luận LLM
    response = await llm.ainvoke(messages)

    # 4. Trả về message mới để StateGraph cập nhật vào state.messages qua add_messages reducer
    return {"messages": [response]}


# Alias để tương thích ngược
agent_node = procurement_node
