"""
Service tầng nghiệp vụ Chatbot RAG (Chat Business Service).
Điều phối truy vấn ngữ cảnh RAG có phân quyền (User Roles RBAC), xây dựng Prompt và gọi LLM Streaming.
"""

import json
import logging
from collections.abc import AsyncGenerator

from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.rag.retrieval.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class ChatService:
    """Service xử lý phản hồi câu hỏi RAG với phân quyền vai trò (RBAC)."""

    def __init__(self, retriever: VectorRetriever, llm_provider: BaseChatModel):
        self.retriever = retriever
        self.llm_provider = llm_provider

    async def generate_rag_response_stream(
        self,
        message: str,
        user_roles: str | None = None,
        top_k: int = 5,
    ) -> AsyncGenerator[str, None]:
        """
        Tạo luồng Server-Sent Events (SSE) phản hồi câu hỏi RAG.
        Đảm bảo lọc tài liệu theo vai trò (user_roles).
        """
        try:
            # 1. Phát sự kiện khởi đầu chat
            yield "event: chat_started\ndata: {}\n\n"

            base_query = message.strip()
            if not base_query:
                yield f"event: token\ndata: {json.dumps({'text': 'Bạn chưa nhập câu hỏi.'})}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # Lời chào đơn giản
            if base_query.lower() in ["hi", "hello", "xin chào", "chào", "alo"]:
                yield "event: citations\ndata: []\n\n"
                yield f"event: token\ndata: {json.dumps({'text': 'Xin chào! Tôi là trợ lý AI thông minh. Tôi có thể giúp gì cho bạn?'})}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 2. Truy vấn ngữ cảnh RAG từ Vector Store với phân quyền RBAC
            search_res = await self.retriever.retrieve_context(
                query=base_query,
                top_k=top_k,
                user_roles=user_roles,
            )

            documents = (
                search_res["documents"][0] if search_res.get("documents") else []
            )
            citations_list = (
                search_res["citations"][0] if search_res.get("citations") else []
            )

            # 3. Trả về trích dẫn tài liệu (Citations SSE Event)
            yield f"event: citations\ndata: {json.dumps(citations_list, ensure_ascii=False, default=str)}\n\n"

            if not documents or not any(doc.strip() for doc in documents):
                logger.warning(
                    "[WARN] [CHAT] No context documents found for query='%s'",
                    base_query,
                )
                yield f"event: token\ndata: {json.dumps({'text': 'Tôi không tìm thấy thông tin phù hợp trong tài liệu được cấp quyền.'})}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 4. Xây dựng Prompt Ngữ Cảnh
            context_str = "\n---\n".join(documents)
            system_prompt = (
                "Bạn là trợ lý AI thông minh của hệ thống Enterprise. "
                "Hãy trả lời câu hỏi của người dùng dựa trên NGỮ CẢNH TÀI LIỆU được cung cấp bên dưới.\n"
                "Quy tắc:\n"
                "1. Chỉ sử dụng thông tin trong phần NGỮ CẢNH TÀI LIỆU. Không tự suy diễn.\n"
                "2. Nếu tài liệu không có thông tin, hãy trả lời: 'Tôi không tìm thấy thông tin này trong tài liệu.'\n"
                "3. Trả lời ngắn gọn, trực tiếp, tự nhiên bằng tiếng Việt."
            )
            user_prompt = f"NGỮ CẢNH TÀI LIỆU:\n{context_str}\n\nCÂU HỎI: {base_query}"

            # 5. Gọi LLM Provider Streaming (LangChain / OpenAI-compatible API)
            logger.info("[CHAT] Calling LLM streaming for query='%s'...", base_query)

            response_chunks: list[str] = []
            # Hỗ trợ stream từ LangChain BaseChatModel
            async for chunk in self.llm_provider.astream(
                [
                    ("system", system_prompt),
                    ("user", user_prompt),
                ]
            ):
                token_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token_text:
                    response_chunks.append(token_text)
                    yield f"event: token\ndata: {json.dumps({'text': token_text}, ensure_ascii=False)}\n\n"

            full_response_text = "".join(response_chunks)
            logger.info(
                "[OK] [CHAT] LLM response completed for query='%s' | Length: %d chars | Response:\n%s",
                base_query,
                len(full_response_text),
                full_response_text,
            )

            yield "event: chat_ended\ndata: {}\n\n"

        except Exception as ex:
            logger.error(
                "[FAIL] Error in RAG Chat Stream for query='%s': %s",
                base_query,
                ex,
                exc_info=True,
            )
            err_payload = json.dumps(
                {"text": "\n[Lỗi kết nối tới mô hình AI hoặc Database]"},
                ensure_ascii=False,
            )
            yield f"event: token\ndata: {err_payload}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"
