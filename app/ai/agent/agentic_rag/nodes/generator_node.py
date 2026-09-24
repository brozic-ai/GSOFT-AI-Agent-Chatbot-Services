import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.agent.agentic_rag.prompts.registry import get_generator_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


def clean_rag_generation_output(text: str, user_query: str = "") -> str:
    """
    Hậu xử lý làm sạch câu trả lời RAG, triệt tiêu hiện tượng mô hình nhỏ (SLM)
    sinh lặp 2 lần (Run-on generation) hoặc dính text câu trả lời tiếp theo sau danh mục trích dẫn.
    """
    if not text or not str(text).strip():
        return ""
    cleaned = str(text).strip()

    # 1. Bóc tách các thẻ kết thúc hoặc marker kỹ thuật
    end_markers = ["[KẾT THÚC]", "[HẾT]", "<|im_end|>", "<|endoftext|>", "</s>"]
    for marker in end_markers:
        cleaned = cleaned.replace(marker, "").strip()

    # 2. Xử lý trường hợp text câu trả lời 2 dính liền vào dấu ngoặc của citation cuối:
    # Ví dụ: "...(Trang 61/139)Quy trình phê duyệt tờ trình mua sắm tài sản trên gAMSPro:..."
    glued_match = re.search(
        r"(\((?:Trang|Slide|Mục)[^\)]+\))([A-ZÀ-Ỹ0-9].*)",
        cleaned,
        re.DOTALL,
    )
    if glued_match:
        cut_pos = glued_match.start(1) + len(glued_match.group(1))
        logger.info(
            "[GENERATOR-CLEANER] Phát hiện text câu trả lời dính liền sau citation: '%s...'. Đã cắt bỏ phần thừa.",
            glued_match.group(2)[:40],
        )
        cleaned = cleaned[:cut_pos].strip()

    # 3. Cắt bỏ nếu sau khối 'Tài liệu tham khảo' xuất hiện một khối câu trả lời hoặc quy trình mới
    ref_match = re.search(
        r"(?:📌\s*)?\*?\*?Tài\s+liệu\s+tham\s+khảo:?\*?\*?",
        cleaned,
        re.IGNORECASE,
    )
    if ref_match:
        ref_start = ref_match.start()
        ref_content = cleaned[ref_start:]
        lines = ref_content.splitlines()
        valid_ref_lines = []
        has_started_items = False

        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                if has_started_items:
                    # Kiểm tra dòng tiếp theo sau dòng trống
                    if idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        if next_line and not re.match(
                            r"^[-*•–\d\[\(]|^(?:Trang|Slide|Mục|Tài liệu)", next_line, re.IGNORECASE
                        ):
                            logger.info(
                                "[GENERATOR-CLEANER] Phát hiện đoạn văn bản mới sau dòng trống tham khảo: '%s...'. Dừng trích dẫn.",
                                next_line[:40],
                            )
                            break
                valid_ref_lines.append(line)
                continue

            # Dòng tiêu đề "Tài liệu tham khảo:"
            if idx == 0 or re.match(
                r"^(?:📌\s*)?\*?\*?Tài\s+liệu\s+tham\s+khảo:?\*?\*?$", line_str, re.IGNORECASE
            ):
                valid_ref_lines.append(line)
                continue

            # Dòng mục trích dẫn hợp lệ: [1]..., - [1]..., - Slide..., • Slide..., v.v.
            is_citation_item = bool(
                re.match(r"^[-*•–]?\s*\[\d+\]", line_str)
                or re.match(
                    r"^[-*•–]?\s*(?:Slide|Trang|Tài liệu|Sổ tay|Quy định|Quy trình)\s+\d+",
                    line_str,
                    re.IGNORECASE,
                )
                or re.match(r"^[-*•–]\s+", line_str)
            )
            if is_citation_item:
                has_started_items = True
                valid_ref_lines.append(line)
            else:
                if has_started_items:
                    logger.info(
                        "[GENERATOR-CLEANER] Phát hiện câu trả lời mới sinh sau danh mục tham khảo: '%s...'. Cắt bỏ từ đây.",
                        line_str[:40],
                    )
                    break
                else:
                    valid_ref_lines.append(line)

        cleaned = cleaned[:ref_start] + "\n".join(valid_ref_lines).rstrip()

    # 4. Kiểm tra nếu tiêu đề câu hỏi / câu mở đầu dòng 1 lặp lại lần 2 ở giữa hoặc cuối câu trả lời
    first_heading = cleaned.splitlines()[0].strip().strip(":*# ") if cleaned.splitlines() else ""
    candidates = []
    if len(first_heading) >= 15:
        candidates.append(first_heading)
    if user_query and len(user_query.strip()) >= 15:
        candidates.append(user_query.strip())

    for cand in candidates:
        cand_esc = re.escape(cand)
        matches = list(re.finditer(rf"(?<=\))\s*{cand_esc}:?|(?:\n|^)\s*{cand_esc}:?", cleaned, re.IGNORECASE))
        if len(matches) > 1:
            second_match = matches[1]
            if second_match.start() > 80:
                logger.info(
                    "[GENERATOR-CLEANER] Phát hiện lặp lại tiêu đề/câu hỏi tại offset %d: '%s'. Cắt bỏ phần sau.",
                    second_match.start(),
                    cand[:40],
                )
                cleaned = cleaned[:second_match.start()].rstrip()
                break

    # 5. Khử lặp 2 nửa chuỗi nguyên văn (LLM lặp lại toàn bộ câu trả lời)
    if len(cleaned) > 80:
        half = len(cleaned) // 2
        p1 = cleaned[:half].strip()
        p2 = cleaned[half:].strip()
        if p1 == p2:
            logger.info("[GENERATOR-CLEANER] Phát hiện lặp 2 nửa chuỗi nguyên văn. Cắt bỏ nửa sau.")
            cleaned = p1

    return cleaned


async def generator_node(state: AgenticRagState) -> dict[str, Any]:
    """Generator Node: Tổng hợp câu trả lời cuối cùng bám sát tài liệu với chuẩn Zero-Hallucination và Inline Footnotes."""
    documents = (
        state.get("documents", [])
        if isinstance(state, dict)
        else getattr(state, "documents", [])
    )
    citations = (
        state.get("citations", [])
        if isinstance(state, dict)
        else getattr(state, "citations", [])
    )
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    messages = (
        state.get("messages", [])
        if isinstance(state, dict)
        else getattr(state, "messages", [])
    )

    if not user_query and messages:
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and getattr(m, "type", "") in ("human", "user"):
                user_query = str(m.content)
                break

    # 1. Trường hợp không có tài liệu (Zero-Hallucination)
    if not documents:
        answer = "Dạ, tôi không tìm thấy tài liệu phù hợp trong phạm vi quyền hạn được cấp của Anh/Chị trên eOffice."
        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
            "citations": [],
        }

    # 2. Sử dụng RagContextBuilder để chuẩn hóa, khử trùng lặp và đóng gói [ĐOẠN n]
    from app.ai.rag.context.builder import RagContextBuilder, determine_max_tokens

    context_str, used_metas, used_citations = RagContextBuilder.build(
        documents=documents,
        metadatas=citations,
    )

    if not context_str.strip():
        answer = "Dạ, tôi không tìm thấy tài liệu phù hợp trong phạm vi quyền hạn được cấp của Anh/Chị trên eOffice."
        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
            "citations": [],
        }

    # 3. Tính toán max_tokens động theo số bước nghiệp vụ trong context
    dynamic_max_tokens = determine_max_tokens(context_str)
    llm = get_chat_model(max_tokens=dynamic_max_tokens)

    # Bắt buộc lấy prompt từ Langfuse — raise RuntimeError nếu không có
    try:
        generator_prompt = get_generator_prompt()
    except RuntimeError as prompt_err:
        logger.error("[GENERATOR-NODE] %s", prompt_err)
        err_answer = (
            "⚠️ Hệ thống hiện không thể kết nối tới kho quản lý Prompt (Langfuse). "
            "Vui lòng thử lại sau ít phút hoặc liên hệ quản trị viên hệ thống."
        )
        return {
            "final_answer": err_answer,
            "messages": [AIMessage(content=err_answer)],
            "citations": [],
        }

    # 4. Thiết lập Stop Sequences ngăn chặn LLM chạy tràn hoặc sinh lặp lại prompt
    stop_sequences = [
        "[KẾT THÚC]",
        "[HẾT]",
        "\n\nNGỮ CẢNH TÀI LIỆU",
        "\nNGỮ CẢNH TÀI LIỆU",
        "\n\nCâu hỏi của cán bộ",
        "\nCâu hỏi của cán bộ",
        "<|im_end|>",
        "<|endoftext|>",
    ]

    response = await llm.ainvoke(
        [
            SystemMessage(content=generator_prompt),
            HumanMessage(
                content=f"Câu hỏi của cán bộ nhân viên: {user_query}\n\nNGỮ CẢNH TÀI LIỆU QUY CHẾ / HDSD:\n{context_str}"
            ),
        ],
        stop=stop_sequences,
    )

    answer = (
        response.content
        if hasattr(response, "content")
        else str(response)
    )

    # Đảm bảo trả về string sạch
    if isinstance(answer, list):
        answer = "".join(str(part) for part in answer)
    else:
        answer = str(answer)

    # 5. Hậu xử lý làm sạch văn bản (Khử lặp, cắt text dính liền)
    answer = clean_rag_generation_output(answer, user_query=user_query)

    return {
        "final_answer": answer,
        "messages": [AIMessage(content=answer)],
        "citations": used_citations if used_citations else citations,
    }
