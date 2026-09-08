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
    # 1. Khởi tạo LLM từ factory kèm Pydantic Output Schema
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(RouterOutput)

    # 2. Lấy Chat Messages trực tiếp từ Langfuse Chat Prompt (System + User)
    user_query = (
        state.get("user_query", "") if isinstance(state, dict) else state.user_query
    )
    chat_history = (
        state.get("chat_history", []) if isinstance(state, dict) else state.chat_history
    )
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

    # 4. Trả về cập nhật thuộc tính route trong State
    return {"route": route_result}
