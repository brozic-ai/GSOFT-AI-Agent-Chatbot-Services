import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / "v1"


def _extract_prompt_text(prompt_obj, role_target: str = "system") -> str:
    """Helper trích xuất nội dung từ Langfuse Chat/Text Prompt."""
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
    Nạp System Prompt cho Procurement Agent:
    - Ở môi trường local dev (ENVIRONMENT=local): Luôn ưu tiên nạp trực tiếp từ file local 'v1/system.md'
      và tự động bổ sung few-shot examples từ 'v1/example.json' để phản ánh ngay các bản vá mới nhất.
    - Ở môi trường production: Nạp từ Langfuse ('procurement') kèm fallback local an toàn.
    """
    from app.core.config import settings

    # 1. Nếu đang ở môi trường local, ưu tiên tuyệt đối file local để dev/test tức thì
    if getattr(settings, "ENVIRONMENT", "").lower() == "local":
        local_content = _load_local_system_prompt()
        if local_content:
            return local_content

    # 2. Ở môi trường khác, thử lấy từ Langfuse trước
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
            content = _extract_prompt_text(prompt_obj, role_target="system")
            if content and len(content.strip()) > 50:
                return content
    except Exception as ex:
        logger.warning("[PROCUREMENT-PROMPT] Lỗi lấy prompt 'procurement' từ Langfuse: %s", ex)

    # 3. Fallback nạp từ file local
    return _load_local_system_prompt() or "Bạn là Trợ lý Mua sắm Doanh nghiệp BVBank (gAMSPro)."


def _load_local_system_prompt() -> str:
    """Helper nạp nội dung system.md kèm các ví dụ few-shot từ example.json."""
    local_path = _DIR / "system.md"
    content = ""
    if local_path.exists():
        try:
            content = local_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("[PROCUREMENT-PROMPT] Không thể đọc file %s: %s", local_path, e)

    examples_path = _DIR / "example.json"
    if examples_path.exists():
        try:
            import json
            examples_data = json.loads(examples_path.read_text(encoding="utf-8"))
            if examples_data:
                example_text = "\n\n## 💡 CÁC VÍ DỤ MINH HỌA XỬ LÝ (FEW-SHOT EXAMPLES):\n"
                for ex_item in examples_data:
                    q = ex_item.get("query", "")
                    calls = ex_item.get("tool_calls", [])
                    resp = ex_item.get("response", "")
                    call_names = ", ".join(f"`{c.get('tool')}`" for c in calls) if calls else "Không cần gọi tool"
                    example_text += f"\n- **Người dùng:** \"{q}\"\n  * **Hành vi AI:** Kích hoạt {call_names}\n  * **Phản hồi mẫu:**\n{resp}\n"
                content += example_text
        except Exception as e:
            logger.warning("[PROCUREMENT-PROMPT] Lỗi đọc %s: %s", examples_path, e)

    return content


def get_user_prompt(
    query: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Nạp và format User Prompt từ Langfuse prompt 'procurement'."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
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
        logger.warning("[PROCUREMENT-USER-PROMPT] Lỗi lấy user prompt từ Langfuse: %s", ex)

    return query


def get_procurement_messages(query: str, chat_history: list[dict] | None = None) -> List[BaseMessage]:
    """Lấy toàn bộ messages (System + User) từ Chat Prompt 'procurement' trên Langfuse."""
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in (chat_history or [])[-6:])
        or "(không có)"
    )
    try:
        client = get_langfuse_client()
        if client:
            prompt_obj = client.get_prompt("procurement", cache_ttl_seconds=60)
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
        logger.warning("[PROCUREMENT-MESSAGES] Lỗi compile prompt procurement từ Langfuse: %s", ex)

    return [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=query),
    ]
