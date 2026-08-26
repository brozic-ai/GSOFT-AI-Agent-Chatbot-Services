"""
Fallback Agent: Chuyên xử lý các câu hỏi chào hỏi, câu hỏi không rõ ý định,
ngoài phạm vi nghiệp vụ hoặc khi các agent khác không thể xử lý.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

FALLBACK_GUIDANCE_MESSAGE = (
    "Xin chào! Tôi là Trợ lý AI của BVBank & gAMSPro. "
    "Tôi có thể hỗ trợ anh/chị các nhóm nghiệp vụ sau:\n"
    "**1. 🛒 Nghiệp vụ gAMSPro (3 phân hệ chính):**\n"
    "   - 📝 **Tờ trình nghiệp vụ:** Tra cứu thông tin, tạo mới và gửi phê duyệt tờ trình mua sắm.\n"
    "   - 📋 **Kế hoạch:** Tra cứu kế hoạch liên kết, kiểm tra hạn mức ngân sách và số dư khả dụng.\n"
    "   - 📦 **Mua sắm:** Tra cứu đơn đặt hàng (PO), tiến độ giao hàng và thông tin nhà cung cấp.\n\n"
    "**2. 📚 Hướng dẫn sử dụng phần mềm:**\n"
    "   - Tra cứu quy trình và tài liệu hướng dẫn thao tác sử dụng các tính năng trên các phần mềm nội bộ đang có.\n\n"
    "**3. 💡 Câu hỏi thường gặp hằng ngày (FAQ):**\n"
    "   - Giải đáp các câu hỏi thường gặp hằng ngày trong công ty (nội quy, giờ làm việc, chế độ nghỉ phép, thủ tục hành chính nội bộ...).\n\n"
    "Anh/chị vui lòng nhập câu hỏi hoặc yêu cầu cụ thể để tôi hỗ trợ nhé!"
)


async def fallback_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Xử lý phản hồi khi Intent được phân loại là Fallback hoặc không xác định được.
    """
    logger.info("[FALLBACK AGENT] Đang xử lý câu hỏi ngoài phạm vi hoặc chào hỏi...")

    return {
        "agent_output": FALLBACK_GUIDANCE_MESSAGE,
        "messages": [AIMessage(content=FALLBACK_GUIDANCE_MESSAGE)],
    }
