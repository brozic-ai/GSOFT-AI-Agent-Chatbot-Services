import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.agent.agentic_rag.nodes.schemas import DocumentGradeOutput
from app.ai.agent.agentic_rag.prompts.registry import get_grader_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


async def grader_node(state: AgenticRagState) -> dict[str, Any]:
    """Node 3: Document Grader — Kiểm tra chất lượng và độ liên quan của tài liệu thu được từ Tool.

    - Trích xuất nội dung `documents` và `citations` từ ToolMessage mới nhất.
    - Gọi LLM với Structured Output `DocumentGradeOutput` để chấm điểm.
    - Cập nhật `documents`, `citations`, `is_relevant`, và `retry_count` vào State.
    """
    messages = (
        state.get("messages", [])
        if isinstance(state, dict)
        else getattr(state, "messages", [])
    )
    retry_count = (
        state.get("retry_count", 0)
        if isinstance(state, dict)
        else getattr(state, "retry_count", 0)
    )

    # 1. Tìm ToolMessage gần nhất trong messages
    tool_content = ""
    for msg in reversed(messages):
        # Kiểm tra ToolMessage hoặc object có content
        if getattr(msg, "type", "") == "tool" or hasattr(msg, "tool_call_id"):
            tool_content = str(msg.content)
            break
        elif (
            isinstance(msg, dict)
            and msg.get("role") == "tool"
            or msg.get("type") == "tool"
        ):
            tool_content = str(msg.get("content", ""))
            break

    # Nếu không tìm thấy bằng loop trên, lấy tin nhắn cuối cùng
    if not tool_content and messages:
        last_msg = messages[-1]
        tool_content = (
            last_msg.content
            if hasattr(last_msg, "content")
            else str(last_msg.get("content", ""))
            if isinstance(last_msg, dict)
            else ""
        )

    # 2. Parse JSON payload do tool trả về
    documents: list[str] = []
    citations: list[dict[str, Any]] = []

    try:
        if tool_content:
            payload = json.loads(tool_content)
            if isinstance(payload, dict):
                documents = payload.get("documents", [])
                citations = payload.get("citations", [])
    except Exception as ex:
        logger.warning(
            "Không thể parse JSON từ ToolMessage content: %s (error: %s)",
            tool_content[:200],
            ex,
        )

    # Nếu không có tài liệu nào trích xuất được -> đánh giá không liên quan
    if not documents:
        return {
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "retry_count": retry_count + 1,
        }

    # 3. Chấm điểm tài liệu bằng LLM Structured Output
    user_query = (
        state.get("user_query", "")
        if isinstance(state, dict)
        else getattr(state, "user_query", "")
    )
    if not user_query and messages:
        # Fallback lấy câu hỏi từ HumanMessage đầu tiên
        for msg in messages:
            if getattr(msg, "type", "") in ("human", "user") or (
                isinstance(msg, dict)
                and msg.get("role") in ("human", "user")
                or msg.get("type") in ("human", "user")
            ):
                user_query = (
                    msg.content
                    if hasattr(msg, "content")
                    else str(msg.get("content", ""))
                )
                break

    context_preview = "\n---\n".join(str(d) for d in documents[:3])

    try:
        llm = get_chat_model().with_structured_output(DocumentGradeOutput)
        grader_prompt = get_grader_prompt()
        result: DocumentGradeOutput = await llm.ainvoke(
            [
                SystemMessage(content=grader_prompt),
                HumanMessage(
                    content=f"Câu hỏi của người dùng: {user_query}\n\nCác đoạn tài liệu thu được:\n{context_preview}"
                ),
            ]
        )
        is_relevant = bool(result.is_relevant)
        logger.info(
            "Document Grader result: is_relevant=%s, reasoning=%s",
            is_relevant,
            result.reasoning,
        )
    except Exception as e:
        logger.exception(
            "Lỗi khi thực thi Document Grader LLM, fallback is_relevant=True: %s",
            e,
        )
        is_relevant = True  # Fallback để không làm gián đoạn luồng trả lời

    update: dict[str, Any] = {
        "documents": documents,
        "citations": citations,
        "is_relevant": is_relevant,
    }
    if not is_relevant:
        update["retry_count"] = retry_count + 1

    return update
