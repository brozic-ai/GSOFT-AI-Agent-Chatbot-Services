import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client



logger = logging.getLogger(__name__)


def _extract_prompt_text(prompt_obj, role_target: str = "system") -> str:
    """Helper trích xuất nội dung text từ Langfuse Chat/Text Prompt."""
    if not prompt_obj:
        return ""
    if isinstance(prompt_obj.prompt, list):
        for msg in prompt_obj.prompt:
            if msg.get("role") == role_target:
                return msg.get("content", "")
        if prompt_obj.prompt:
            return prompt_obj.prompt[0].get("content", "")
    elif isinstance(prompt_obj.prompt, str):
        return prompt_obj.prompt
    return str(prompt_obj.prompt)


def get_system_prompt() -> str:
    """
    Nạp System Prompt cho RAG Knowledge Agent từ Langfuse ('rag_system').
    Tự động cache 60s và fallback an toàn.
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[RAG-SYSTEM-PROMPT] Lỗi lấy prompt 'rag_system' từ Langfuse: %s", ex)

    return "Bạn là Trợ lý Tra cứu Quy chế, Chính sách & Sổ tay Nghiệp vụ BVBank."



DEFAULT_GENERATOR_PROMPT = """Bạn là Trợ lý AI Chuyên gia Quản trị Tài sản & Quy chế Nghiệp vụ Ngân hàng Bản Việt (BVBank).
Nhiệm vụ của bạn là giải đáp thắc mắc của Cán bộ Nhân viên (CBNV) dựa HOÀN TOÀN và TUYỆT ĐỐI vào các đoạn tài liệu quy trình, sổ tay hướng dẫn được cung cấp.

QUY TẮC PHẢN HỒI BẮT BUỘC:
1. NGUYÊN TẮC ZERO-HALLUCINATION:
   - Chỉ sử dụng các dữ kiện, quy định, bước thực hiện có trong các đoạn tài liệu được cung cấp.
   - Tuyệt đối KHÔNG tự suy diễn, phỏng đoán, thêm thắt thông tin ngoài tài liệu.
   - Nếu trong các đoạn trích dẫn không có thông tin để trả lời câu hỏi, hãy lịch sự thông báo rõ ràng: "Tôi không tìm thấy thông tin phù hợp trong tài liệu quy chế/HDSD được cấp quyền truy cập."

2. ĐỊNH DẠNG VÀ TRÍCH DẪN INLINE FOOTNOTE (BẮT BUỘC):
   - Khi trình bày các bước thực hiện, điều kiện hoặc quy định cụ thể, bạn BẮT BUỘC chèn trích dẫn inline footnote dạng `[1]`, `[2]`... ngay sau câu hoặc bước đó tương ứng với số thứ tự của [ĐOẠN X] trong tài liệu cung cấp.
     Ví dụ:
     "Bước 1: Đăng nhập vào phần mềm gAMSPro bằng tài khoản phân quyền [1]."
     "Bước 2: Vào phân hệ Quản lý tài sản, chọn Kế hoạch mua sắm và nhấn Thêm mới [1][2]."
   - Nếu tài liệu là slide hoặc quy trình từng bước, hãy trình bày dạng danh sách có đánh số thứ tự (Bước 1, Bước 2...) rõ ràng, mạch lạc, chi tiết nút bấm trên hệ thống.

3. PHẦN TÀI LIỆU THAM KHẢO Ở CUỐI:
   - Ở cuối câu trả lời, luôn có phần tổng kết danh mục tài liệu tham khảo theo định dạng:
     📌 **Tài liệu tham khảo:**
     - [1] <Tên tài liệu / Slide> (Trang/Slide ..., Mục ...)
     - [2] ...

4. PHONG CÁCH DIỄN ĐẠT:
   - Chuyên nghiệp, lịch thiệp, chuẩn mực ngân hàng.
   - Trực diện, không lan man.
"""


def get_generator_prompt() -> str:
    """
    Nạp Prompt cho Generator Node từ Langfuse ('rag_generator').
    """
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_generator", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content:
                return content
    except Exception as ex:
        logger.warning("[RAG-GENERATOR-PROMPT] Lỗi lấy prompt 'rag_generator' từ Langfuse: %s", ex)

    return DEFAULT_GENERATOR_PROMPT


def get_user_prompt(
    query: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Nạp và format User Prompt từ Langfuse prompt 'rag_system'."""
    history_text = (
        "\n".join(
            f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:]
        )
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                    )
                    if isinstance(compiled, list):
                        for m in compiled:
                            if m.get("role") == "user":
                                return m.get("content", query)
                except Exception:
                    pass
                user_content = _extract_prompt_text(prompt_obj, role_target="user")
                if user_content:
                    return user_content
    except Exception as ex:
        logger.warning("[RAG-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)

    return query


def get_rag_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """Lấy toàn bộ messages (System + User) từ Chat Prompt 'rag_system' trên Langfuse."""
    history_text = (
        "\n".join(
            f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:]
        )
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("rag_system", cache_ttl_seconds=60)
            if prompt_obj:
                try:
                    compiled = prompt_obj.compile(
                        query=query,
                        chat_history=history_text,
                    )
                except Exception:
                    compiled = prompt_obj.compile()

                messages: List[BaseMessage] = []
                if isinstance(compiled, list):
                    for m in compiled:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        if role == "system":
                            messages.append(SystemMessage(content=content))
                        elif role == "user":
                            messages.append(HumanMessage(content=content))
                        elif role in ("assistant", "ai"):
                            messages.append(AIMessage(content=content))

                    if len(messages) == 1 and isinstance(messages[0], SystemMessage):
                        messages.append(HumanMessage(content=query))

                    if messages:
                        return messages
    except Exception as ex:
        logger.warning("[RAG-MESSAGES] Lỗi compile prompt rag_system từ Langfuse: %s", ex)

    return [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=query),
    ]
