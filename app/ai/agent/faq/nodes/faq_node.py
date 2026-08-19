"""
FAQ Agent Node: Tra cứu và trả lời các câu hỏi thường gặp (FAQ Knowledge Base).
(Stub Interface chuẩn kết nối với Orchestrator)
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


async def faq_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Xử lý câu hỏi thường gặp (FAQ).
    Được thiết kế theo chuẩn Interface để bạn đồng nghiệp tích hợp logic chuyên sâu.
    """
    user_query = state.get("user_query", "")
    logger.info("[FAQ AGENT] Đang xử lý câu hỏi FAQ: '%s'", user_query[:80])

    # Placeholder / Stub logic cho FAQ
    response_content = (
        f"💡 [FAQ Bot]: Đây là giải đáp cho câu hỏi thường gặp liên quan đến '{user_query}'. "
        f"(Hệ thống FAQ đang được tích hợp dữ liệu câu hỏi thường gặp của BVBank)."
    )

    return {
        "agent_output": response_content,
        "messages": [AIMessage(content=response_content)],
    }
