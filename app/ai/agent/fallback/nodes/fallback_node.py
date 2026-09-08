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

RAG_NO_DOCS_MESSAGE = (
    "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."
)

FAQ_NO_MATCH_MESSAGE = (
    "ℹ️ Hiện tại tôi chưa tìm thấy thông tin liên quan đến câu hỏi của bạn trong cơ sở dữ liệu FAQ nội bộ BVBank.\n"
    "Bạn vui lòng kiểm tra lại câu hỏi hoặc liên hệ **Bộ phận Hỗ trợ Nội bộ BVBank** để được hỗ trợ chi tiết nhé! 😊"
)


async def fallback_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Xử lý phản hồi Fallback đa ngữ cảnh (Central Fallback Hub):
    - Khi được gọi từ RAG Agent (AgenticRagState có 'documents' rỗng): Trả về thông báo Zero-Hallucination không tìm thấy tài liệu.
    - Khi được gọi từ FAQ Agent: Trả về thông báo không tìm thấy FAQ.
    - Mặc định (Orchestrator Intent): Trả về menu hướng dẫn nghiệp vụ toàn diện.
    """
    # 1. Ngữ cảnh RAG Agent (AgenticRagState)
    if "documents" in state and not state.get("documents"):
        logger.info("[FALLBACK] Xử lý ngữ cảnh RAG Miss: không tìm thấy tài liệu quy chế.")
        return {
            "final_answer": RAG_NO_DOCS_MESSAGE,
            "agent_output": RAG_NO_DOCS_MESSAGE,
            "messages": [AIMessage(content=RAG_NO_DOCS_MESSAGE)],
            "documents": [],
            "citations": [],
            "is_relevant": False,
        }

    # 2. Ngữ cảnh FAQ Agent (FAQState)
    if "retrieved_faqs" in state and not state.get("retrieved_faqs"):
        logger.info("[FALLBACK] Xử lý ngữ cảnh FAQ Miss: không tìm thấy câu hỏi FAQ phù hợp.")
        return {
            "final_answer": FAQ_NO_MATCH_MESSAGE,
            "agent_output": FAQ_NO_MATCH_MESSAGE,
            "messages": [AIMessage(content=FAQ_NO_MATCH_MESSAGE)],
            "citations": [],
        }

    # 3. Ngữ cảnh Orchestrator Chitchat / Out-of-scope
    logger.info("[FALLBACK AGENT] Đang xử lý câu hỏi ngoài phạm vi hoặc chào hỏi...")
    return {
        "final_answer": FALLBACK_GUIDANCE_MESSAGE,
        "agent_output": FALLBACK_GUIDANCE_MESSAGE,
        "messages": [AIMessage(content=FALLBACK_GUIDANCE_MESSAGE)],
    }

