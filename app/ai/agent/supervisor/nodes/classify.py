import json
import logging
import re

from app.ai.agent.supervisor.prompts.registry import get_supervisor_messages
from app.ai.agent.supervisor.schemas import IntentType, RouterOutput
from app.ai.agent.supervisor.state import SupervisorState
from app.llmops.factory import get_router_model

logger = logging.getLogger(__name__)


async def classify_intent_node(state: SupervisorState) -> dict:
    """
    Node phân loại Intent của người dùng (FAQ, RAG, PROCUREMENT hoặc FALLBACK)
    sử dụng LLM ép kiểu Structured Output (RouterOutput Pydantic Schema).
    Đảm bảo các truy vấn Tờ trình, Kế hoạch, PO, Mua sắm được định tuyến chính xác đến 'procurement'.
    """
    user_query = (
        state.get("user_query", "") if isinstance(state, dict) else state.user_query
    )
    chat_history = (
        state.get("chat_history", []) if isinstance(state, dict) else state.chat_history
    )

    # Only inherit an intent for an actual follow-up. A manual mentioning
    # gAMSPro/PO is not evidence of a live procurement operation.
    clean_q = (user_query or "").strip().lower().strip("*_\"'")
    followup = bool(
        re.search(
            r"^(?:xem\s+)?(?:tiếp\b|trang\s+\d+|trang\s+sau|kế\s+tiếp|thêm\b)"
            r"|^(?:còn\s+nữa|bước\s+tiếp|có\s+hướng\s+dẫn|liệt\s+kê\s+(?:tiếp|tất\s+cả))"
            r"|^(?:ok|đồng\s+ý|có|được|ừ|yes)[.!?\s]*$",
            clean_q,
        )
    )
    last_assistant = next(
        (
            str(h.get("content", ""))
            for h in reversed(chat_history or [])
            if h.get("role") in ("assistant", "ai")
        ),
        "",
    )
    last_user = next(
        (
            str(h.get("content", ""))
            for h in reversed(chat_history or [])
            if h.get("role") in ("user", "human")
        ),
        "",
    )
    instruction_pattern = r"\b(?:hướng dẫn|quy trình|các bước|bước tiếp|giải thích|tài liệu|cách|làm sao)\b"
    asks_instructions = bool(re.search(instruction_pattern, clean_q))
    history_instructions = bool(
        re.search(instruction_pattern, (last_user or last_assistant).lower())
    )
    history_records = bool(
        re.search(
            r"\b(?:PUR/\d{4}/\d+|TRRD\d+|PO[/\-]\w+|danh sách tờ trình|ngân sách còn lại)\b",
            last_assistant,
            re.IGNORECASE,
        )
    )
    # A new action is not a request to continue a manual, even if prefixed
    # with "tiếp tục". Let the model resolve it against the full history.
    if not asks_instructions and re.search(
        r"\b(?:tạo|gửi|phê duyệt|duyệt|hủy|xóa|cập nhật|kiểm tra)\b", clean_q
    ):
        followup = False
    intent = None
    if followup and last_assistant:
        if asks_instructions or history_instructions:
            intent = "rag"
        elif history_records:
            intent = "procurement"
    if intent:
        context = last_user or last_assistant[:2000]
        route_result = RouterOutput(
            reasoning="Câu hỏi tiếp nối kế thừa đúng ngữ cảnh hướng dẫn hoặc hồ sơ thực tế.",
            intent=intent,
            query=f"{user_query}\nNgữ cảnh câu hỏi trước: {context}",
            confidence=0.95,
        )
        return {"route": route_result, "intent": intent}

    # 1. Khởi tạo Router LLM chuyên trách từ factory kèm Pydantic Output Schema
    llm = get_router_model(temperature=0.0, max_tokens=512)

    # 2. Lấy Chat Messages trực tiếp từ Langfuse/Local Chat Prompt (System + User)
    messages = get_supervisor_messages(query=user_query, chat_history=chat_history)

    # 3. Gọi LLM suy luận phân loại Intent
    try:
        structured_llm = llm.with_structured_output(RouterOutput)
        route_result = RouterOutput.model_validate(
            await structured_llm.ainvoke(messages)
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning(
            "[SUPERVISOR-CLASSIFY] with_structured_output failed (%s). Falling back to direct JSON parsing.",
            ex,
        )
        raw_res = await llm.ainvoke(messages)
        raw_text = raw_res.content if hasattr(raw_res, "content") else str(raw_res)
        # Loại bỏ markdown code blocks (```json ... ```) nếu có
        clean_text = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", str(raw_text).strip(), flags=re.MULTILINE
        ).strip()
        try:
            data = json.loads(clean_text)
            route_result = RouterOutput(**data)
        except Exception:
            match = re.search(r"\{.*\}", clean_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                route_result = RouterOutput(**data)
            else:
                raise

    # Scope is a separate model judgement. For FAQ, explicit workplace terms
    # take precedence over a mistaken scope flag from a small classifier.
    company_faq = bool(
        re.search(
            r"\b(?:bvbank|bản việt|công ty|ngân hàng|nội bộ|nhân viên|nhân sự|"
            r"nghỉ phép|nghỉ lễ|giờ làm|chấm công|trang phục|đào tạo|lương|"
            r"phúc lợi|bảo hiểm|helpdesk|hr|it|nội quy)\b",
            user_query,
            re.IGNORECASE,
        )
    )
    if (
        route_result.intent == IntentType.FAQ
        and not route_result.in_scope
        and not company_faq
    ):
        route_result = route_result.model_copy(update={"intent": IntentType.FALLBACK})

    # 4. Trả về cập nhật thuộc tính route và intent trong State
    intent_val = (
        route_result.intent.value
        if hasattr(route_result.intent, "value")
        else str(route_result.intent)
    )
    return {"route": route_result, "intent": intent_val}
