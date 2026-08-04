from abc import ABC, abstractmethod
from typing import Any

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any
    ) -> str:
        """Gửi system + user prompt tới LLM, trả về text response."""
        raise NotImplementedError
        # ...

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict | None = None) -> dict:
        """Gửi prompt, ép trả về JSON đã parse sẵn thành dict."""
        raise NotImplementedError