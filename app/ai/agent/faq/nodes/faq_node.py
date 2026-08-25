"""
FAQ Agent Node — Node chính điều phối hội thoại cho FAQ Agent.

Nhận FAQState, đưa System Prompt vào messages, bind tool search_faq_knowledge_base,
gọi LLM để xử lý theo pattern ReAct (Reason + Act).
"""

import logging

from langchain_core.messages import BaseMessage, SystemMessage

from app.ai.agent.faq.prompts.registry import PromptLoader
from app.ai.agent.faq.state import FAQState
from app.ai.agent.faq.tools import FAQ_TOOLS
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

# Load System Prompt một lần duy nhất khi module được import (tránh đọc file nhiều lần)
_SYSTEM_PROMPT: str = PromptLoader(task="faq").load_system()


async def faq_agent_node(state: FAQState) -> dict[str, list[BaseMessage]]:
    """Node chính của FAQ Agent — LLM suy luận và quyết định gọi tool hay trả lời thẳng.

    Luồng:
    - Nếu cần tra cứu FAQ → LLM sinh tool_calls → ToolNode xử lý → quay lại node này.
    - Nếu đã có kết quả tool → LLM tổng hợp câu trả lời thân thiện → kết thúc.
    - Nếu không tìm thấy FAQ (tool trả về found=false) → LLM kích hoạt Fallback theo System Prompt.
    """
    messages = (
        list(state.get("messages", []))
        if isinstance(state, dict)
        else list(state.messages)
    )

    # Đưa System Prompt vào đầu danh sách nếu chưa có
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages

    # Khởi tạo LLM và bind FAQ search tool
    llm = get_chat_model().bind_tools(FAQ_TOOLS)

    # Gọi LLM (async)
    response = await llm.ainvoke(messages)
    logger.debug(
        "[FAQ AGENT NODE] LLM response: tool_calls=%s",
        bool(getattr(response, "tool_calls", None)),
    )

    return {"messages": [response]}
