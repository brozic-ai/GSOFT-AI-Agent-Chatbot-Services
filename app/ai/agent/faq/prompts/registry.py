import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llmops.langfuse import get_langfuse_client

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent


class PromptLoader:
    def __init__(self, task: str = "faq", version: str = "v1"):
        if (PROMPTS_DIR / version).exists():
            self.task_dir = PROMPTS_DIR / version
        elif task and (PROMPTS_DIR / task / version).exists():
            self.task_dir = PROMPTS_DIR / task / version
        else:
            self.task_dir = PROMPTS_DIR / version

        if not self.task_dir.exists():
            raise FileNotFoundError(f"Không tìm thấy prompt: {task}/{version}")

    def load_system(self) -> str:
        # Thử lấy từ Langfuse trước nếu có cấu hình
        try:
            client = get_langfuse_client()
            if client:
                prompt_obj = client.get_prompt("faq", cache_ttl_seconds=60)
                if prompt_obj:
                    if isinstance(prompt_obj.prompt, list):
                        for m in prompt_obj.prompt:
                            if m.get("role") == "system":
                                return m.get("content", "")
                    elif isinstance(prompt_obj.prompt, str):
                        return prompt_obj.prompt
        except Exception:
            pass

        sys_file = self.task_dir / "system.md"
        if sys_file.exists():
            return sys_file.read_text(encoding="utf-8")
        return "Bạn là Trợ lý AI trả lời câu hỏi thường gặp (FAQ)."

    def load_user(self, **kwargs) -> str:
        user_file = self.task_dir / "user.md"
        if user_file.exists():
            template = user_file.read_text(encoding="utf-8")
            return template.format(**kwargs) if kwargs else template
        return kwargs.get("query", "")

