import json
import logging
import re
from app.ai.agent.supervisor.prompts.registry import get_supervisor_messages
from app.ai.agent.supervisor.schemas import RouterOutput
from app.ai.agent.supervisor.state import SupervisorState
from app.llmops.factory import get_chat_model

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

    # 0. Fast-path heuristic cho pagination / follow-up / anaphora trong procurement (Zero-Latency, 100% Accuracy)
    clean_q = (user_query or "").strip().lower().strip("*_\"'")
    is_pagination = bool(
        re.search(
            r"^(xem\s+)?(tiếp|trang\s+\d+|trang\s+sau|kế\s+tiếp|thêm)|liệt\s+kê\s+(tất\s+cả|hết)",
            clean_q,
        )
    )
    is_ordinal_to_trinh = bool(
        re.search(
            r"(chi\s+tiết\s+)?(tờ\s+trình|hồ\s+sơ|đơn|mục|cái)\s+(đầu\s+tiên|thứ\s+\d+|số\s+\d+)",
            clean_q,
        )
    )
    is_pur_detail = bool(re.search(r"(xem\s+chi\s+tiết|thông\s+tin)\s+pur/", clean_q))
    is_followup_confirmation = bool(
        re.search(
            r"^(có\b|đồng\s*ý|được|ok\b|ừ\b|yes\b|tiến\s*hành|thực\s*hiện|kiểm\s*tra|tra\s*cứu|xem\s*giúp)",
            clean_q,
        )
        or any(
            phrase in clean_q
            for phrase in [
                "kiểm tra giúp",
                "kiểm tra giùm",
                "kiểm tra hộ",
                "tra cứu giúp",
                "kiểm tra ngân sách",
                "kiểm tra kế hoạch",
                "xem ngân sách",
                "xem kế hoạch",
            ]
        )
    )

    if (is_pagination or is_ordinal_to_trinh or is_pur_detail or is_followup_confirmation) and chat_history:
        last_assistant_msg = ""
        for h in reversed(chat_history):
            if h.get("role") in ("assistant", "ai"):
                last_assistant_msg = h.get("content", "")
                break

        procurement_keywords = [
            "tờ trình",
            "pur/",
            "gamspro",
            "kế hoạch",
            "ngân sách",
            "đơn hàng",
            "đơn đặt hàng",
            "po",
        ]
        if any(kw in last_assistant_msg.lower() for kw in procurement_keywords):
            logger.info(
                "[SUPERVISOR-CLASSIFY] Fast-path định tuyến 'procurement' cho câu hỏi tiếp nối / xác nhận: '%s'",
                clean_q,
            )
            route_result = RouterOutput(
                reasoning=(
                    "Người dùng đang xác nhận thực hiện thao tác tiếp nối hoặc điều hướng hồ sơ gAMSPro từ ngữ cảnh trước."
                ),
                intent="procurement",
                query=user_query,
                confidence=1.0,
            )
            return {"route": route_result, "intent": "procurement"}

    # 1. Khởi tạo LLM từ factory kèm Pydantic Output Schema
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(RouterOutput)

    # 2. Lấy Chat Messages trực tiếp từ Langfuse/Local Chat Prompt (System + User)
    messages = get_supervisor_messages(query=user_query, chat_history=chat_history)

    # 3. Gọi LLM suy luận phân loại Intent
    try:
        route_result: RouterOutput = await structured_llm.ainvoke(messages)
    except Exception as ex:
        logger.warning("[SUPERVISOR-CLASSIFY] with_structured_output failed (%s). Falling back to direct JSON parsing.", ex)
        raw_res = await llm.ainvoke(messages)
        raw_text = raw_res.content if hasattr(raw_res, "content") else str(raw_res)
        # Loại bỏ markdown code blocks (```json ... ```) nếu có
        clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw_text).strip(), flags=re.MULTILINE).strip()
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

    # 4. Trả về cập nhật thuộc tính route và intent trong State
    intent_val = (
        route_result.intent.value
        if hasattr(route_result.intent, "value")
        else str(route_result.intent)
    )
    return {"route": route_result, "intent": intent_val}
