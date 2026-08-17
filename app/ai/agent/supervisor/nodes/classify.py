from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.agent.supervisor.prompts.registry import get_system_prompt, get_user_prompt
from app.ai.agent.supervisor.schemas import RouterOutput
from app.ai.agent.supervisor.state import SupervisorState
from app.llmops.factory import get_chat_model


async def classify_intent_node(state: SupervisorState) -> dict:
    """
    Node phân loại Intent của người dùng (FAQ, RAG, PROCUREMENT hoặc FALLBACK)
    sử dụng LLM ép kiểu Structured Output (RouterOutput Pydantic Schema).
    Đảm bảo các truy vấn Tờ trình, Kế hoạch, PO, Mua sắm được định tuyến chính xác đến 'procurement'.
    """
    # 1. Khởi tạo LLM từ factory kèm Pydantic Output Schema
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(RouterOutput)

    # 2. Lấy System Prompt & User Prompt
    system_prompt = get_system_prompt()
    user_query = (
        state.get("user_query", "") if isinstance(state, dict) else state.user_query
    )
    chat_history = (
        state.get("chat_history", []) if isinstance(state, dict) else state.chat_history
    )
    user_prompt = get_user_prompt(query=user_query, chat_history=chat_history)

    # 3. Gọi LLM suy luận phân loại Intent
    route_result: RouterOutput = await structured_llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    # 4. Trả về cập nhật thuộc tính route trong State
    return {"route": route_result}
