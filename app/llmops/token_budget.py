"""Count the serving model's chat template before sending a RAG completion.

llama.cpp exposes apply-template/tokenize alongside its OpenAI API. Other
backends use a conservative UTF-8 byte bound, never a chars/token assumption.
"""

import logging
from collections.abc import Sequence

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.core.model_levels import normalize_model_level

logger = logging.getLogger(__name__)


class PromptBudgetError(ValueError):
    """The fixed prompt/query cannot fit without changing their meaning."""


class PromptTokenCounter:
    def __init__(self, level: str):
        level = normalize_model_level(level)
        self.model = getattr(settings, f"MODEL_LEVEL_{level.upper()}_MODEL")
        self.window = settings.LLM_CONTEXT_WINDOW
        self.native = getattr(settings, f"MODEL_LEVEL_{level.upper()}_PROVIDER") in {
            "vllm",
            "ollama",
            "openai_compat",
        }
        self.client = None

    async def __aenter__(self):
        if self.native:
            self.client = httpx.AsyncClient(
                base_url=settings.LLM_BASE_URL.rstrip("/").removesuffix("/v1"),
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                timeout=settings.LLM_TOKENIZER_TIMEOUT,
            )
            try:
                response = await self.client.get("/v1/models")
                response.raise_for_status()
                for item in response.json().get("data", []):
                    if item.get("id") == self.model:
                        served_window = item.get("meta", {}).get("n_ctx")
                        if isinstance(served_window, int) and served_window > 0:
                            self.window = min(self.window, served_window)
                        break
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                logger.warning(
                    "Cannot read serving context window; using configured limit"
                )
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    async def count(self, messages: Sequence[BaseMessage]) -> int:
        if self.native and self.client:
            try:
                roles = {"human": "user", "ai": "assistant", "system": "system"}
                response = await self.client.post(
                    "/apply-template",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": roles[m.type], "content": str(m.content)}
                            for m in messages
                        ],
                        "add_generation_prompt": True,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                response.raise_for_status()
                prompt = response.json()["prompt"]
                response = await self.client.post(
                    "/tokenize",
                    json={
                        "model": self.model,
                        "content": prompt,
                        "add_special": True,
                        "parse_special": True,
                    },
                )
                response.raise_for_status()
                tokens = response.json()["tokens"]
                if not isinstance(tokens, list):
                    raise TypeError("Invalid tokenizer response")
                return len(tokens)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                self.native = False
                logger.warning(
                    "Native tokenizer unavailable; using conservative UTF-8 token bound"
                )
        # Byte-level tokenizers cannot use more than one token per byte of text.
        # Reserve additional room for role/template delimiters.
        return 256 + sum(len(str(m.content).encode("utf-8")) + 32 for m in messages)


async def prepare_rag_prompt(
    *, level, system_prompt, query, history, documents, citations, max_chars, max_tokens
):
    from app.ai.rag.context.builder import RagContextBuilder

    # Only conversational turns are useful here; never copy tools/system messages
    # from the outer graph into the grounding prompt.
    previous = [m for m in history if m.type in ("human", "ai") and m.content][-6:]
    if previous and previous[-1].type == "human" and str(previous[-1].content) == query:
        previous.pop()  # current user query is supplied explicitly below

    def build(chars):
        context, _, used = RagContextBuilder.build(
            documents, citations, max_context_chars=chars
        )
        messages = [
            SystemMessage(content=system_prompt),
            *previous,
            HumanMessage(
                content=(
                    f"Câu hỏi của cán bộ nhân viên: {query}\n\n"
                    "Chỉ dùng tài liệu dưới đây làm căn cứ; lịch sử chỉ giúp xác định đối tượng câu hỏi.\n"
                    f"NGỮ CẢNH TÀI LIỆU QUY CHẾ / HDSD:\n{context}"
                )
            ),
        ]
        return messages, used, context

    async with PromptTokenCounter(level) as counter:
        available = counter.window - max_tokens - settings.LLM_CONTEXT_SAFETY_TOKENS
        base, _, _ = build(0)
        base_tokens = await counter.count(base)
        while previous and base_tokens + 256 > available:
            previous.pop(0)
            base, _, _ = build(0)
            base_tokens = await counter.count(base)
        if base_tokens + 64 >= available:
            raise PromptBudgetError(
                "System prompt and question exceed the model input budget"
            )

        chars = max_chars
        for _ in range(12):
            messages, used, context = build(chars)
            prompt_tokens = await counter.count(messages)
            if prompt_tokens <= available and context.strip():
                return (
                    messages,
                    used,
                    {
                        "effective_model_level": level,
                        "prompt_tokens": prompt_tokens,
                        "max_output_tokens": max_tokens,
                        "context_window": counter.window,
                        "context_truncated": chars < max_chars
                        or len(used) < len(documents)
                        or "[Nội dung còn lại đã được lược bớt.]" in context,
                    },
                )
            if not context.strip():
                break
            # Shrink only the retrieved context, preserving the system/query.
            # Recount the complete rendered chat template after each change.
            ratio = (available - base_tokens) / max(1, prompt_tokens - base_tokens)
            chars = min(chars - 1, int(len(context) * min(0.85, ratio * 0.95)))
            if chars <= 0:
                break
        raise PromptBudgetError("No grounded document fits the model input budget")
