"""
Service tầng nghiệp vụ Chatbot RAG (Chat Business Service).
Điều phối truy vấn ngữ cảnh RAG có phân quyền (User Roles RBAC), xây dựng Prompt,
gọi LLM Streaming và quản lý lịch sử hội thoại (Chat History).
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional, List, Dict, Any
from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.rag.retrieval.retriever import VectorRetriever
from app.modules.chat.repository import ChatRepository

logger = logging.getLogger(__name__)

# Số tin nhắn lịch sử tối đa truyền vào LLM làm ngữ cảnh
HISTORY_LIMIT = 10


class ChatService:
    """Service xử lý phản hồi câu hỏi RAG với phân quyền vai trò (RBAC) và lịch sử hội thoại."""

    def __init__(self, retriever: VectorRetriever, llm_provider: BaseChatModel, chat_repository: ChatRepository):
        self.retriever = retriever
        self.llm_provider = llm_provider
        self.chat_repo = chat_repository

    # ── Conversation Management ──

    def create_conversation(self, user_id: str) -> int:
        """Tạo phiên hội thoại mới. Trả về conversation_id (int)."""
        return self.chat_repo.create_conversation(user_id=user_id)

    def get_conversation(self, conversation_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin phiên hội thoại, kiểm tra quyền sở hữu theo user_id."""
        return self.chat_repo.get_conversation(conversation_id=conversation_id, user_id=user_id)

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách lịch sử các phiên hội thoại của người dùng."""
        return self.chat_repo.list_conversations(user_id=user_id)

    def get_chat_history(self, conversation_id: int, limit: int = HISTORY_LIMIT) -> List[Dict[str, Any]]:
        """Lấy N tin nhắn gần nhất trong phiên hội thoại."""
        return self.chat_repo.get_chat_history(conversation_id=conversation_id, limit=limit)

    def delete_conversation(self, conversation_id: int, user_id: str) -> bool:
        """Xóa phiên hội thoại và toàn bộ tin nhắn liên quan."""
        return self.chat_repo.delete_conversation(conversation_id=conversation_id, user_id=user_id)

    # ── RAG Streaming ──

    async def generate_rag_response_stream(
        self,
        message: str,
        conversation_id: Optional[int] = None,
        user_id: Optional[str] = None,
        user_roles: Optional[str] = None,
        top_k: int = 5,
        request: Optional[Request] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Tạo luồng Server-Sent Events (SSE) phản hồi câu hỏi RAG.
        Tích hợp lịch sử hội thoại vào ngữ cảnh Prompt để bot nhớ các câu hỏi trước.

        Luồng xử lý:
        1. Lấy lịch sử tin nhắn từ DB (nếu có conversation_id).
        2. Lưu câu hỏi mới của User vào DB.
        3. Truy vấn RAG từ Vector Store (có RBAC).
        4. Xây dựng Prompt kết hợp ngữ cảnh tài liệu + lịch sử hội thoại.
        5. Stream câu trả lời từ LLM; nối lại và lưu câu trả lời vào DB sau khi hoàn tất.
        """
        try:
            # Phát sự kiện khởi đầu chat
            yield "event: chat_started\ndata: {}\n\n"

            if request and await request.is_disconnected():
                return

            base_query = message.strip()
            if not base_query:
                yield f"event: token\ndata: {json.dumps({'text': 'Bạn chưa nhập câu hỏi.'})}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # Lời chào đơn giản — không cần RAG, không lưu lịch sử
            if base_query.lower() in ["hi", "hello", "xin chào", "chào", "alo"]:
                yield "event: citations\ndata: []\n\n"
                yield f"event: token\ndata: {json.dumps({'text': 'Xin chào! Tôi là trợ lý AI thông minh. Tôi có thể giúp gì cho bạn?'})}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 1. Lấy lịch sử hội thoại từ DB
            history: List[Dict[str, Any]] = []
            is_first_message = True
            if conversation_id:
                if request and await request.is_disconnected():
                    return
                message_count = self.chat_repo.get_message_count(conversation_id)
                is_first_message = (message_count == 0)
                if message_count > 0:
                    history = self.chat_repo.get_chat_history(conversation_id, limit=HISTORY_LIMIT)

            # 2. Lưu câu hỏi của User vào DB
            if conversation_id:
                if request and await request.is_disconnected():
                    return
                self.chat_repo.save_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=base_query,
                )
                # Tự động đặt tiêu đề từ câu hỏi đầu tiên
                if is_first_message:
                    self.chat_repo.update_conversation_title(conversation_id, base_query)

            # 3. Truy vấn ngữ cảnh RAG từ Vector Store với phân quyền RBAC
            search_res = await self.retriever.retrieve_context(
                query=base_query,
                top_k=top_k,
                user_roles=user_roles,
            )

            if request and await request.is_disconnected():
                return

            documents = search_res["documents"][0] if search_res.get("documents") else []
            citations_list = search_res["citations"][0] if search_res.get("citations") else []

            # Trả về trích dẫn tài liệu (Citations SSE Event)
            yield f"event: citations\ndata: {json.dumps(citations_list, ensure_ascii=False, default=str)}\n\n"

            if not documents or not any(doc.strip() for doc in documents):
                no_info_msg = "Tôi không tìm thấy thông tin phù hợp trong tài liệu được cấp quyền."
                yield f"event: token\ndata: {json.dumps({'text': no_info_msg})}\n\n"
                # Lưu câu trả lời "không tìm thấy" vào DB
                if conversation_id:
                    self.chat_repo.save_message(conversation_id=conversation_id, role="assistant", content=no_info_msg)
                    self.chat_repo.touch_conversation(conversation_id)
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 4. Xây dựng Prompt kết hợp ngữ cảnh tài liệu + lịch sử hội thoại
            context_str = "\n---\n".join(documents)
            system_prompt = (
                "Bạn là trợ lý AI thông minh của hệ thống Enterprise. "
                "Hãy trả lời câu hỏi của người dùng dựa trên NGỮ CẢNH TÀI LIỆU được cung cấp bên dưới.\n"
                "Quy tắc:\n"
                "1. Chỉ sử dụng thông tin trong phần NGỮ CẢNH TÀI LIỆU. Không tự suy diễn.\n"
                "2. Nếu tài liệu không có thông tin, hãy trả lời: 'Tôi không tìm thấy thông tin này trong tài liệu.'\n"
                "3. Trả lời ngắn gọn, trực tiếp, tự nhiên bằng tiếng Việt.\n\n"
                f"NGỮ CẢNH TÀI LIỆU:\n{context_str}"
            )

            # Xây dựng danh sách messages kèm lịch sử hội thoại
            messages_for_llm = [("system", system_prompt)]
            for hist_msg in history:
                role = hist_msg["role"]
                if role in ("user", "assistant"):
                    messages_for_llm.append((role, hist_msg["content"]))
            messages_for_llm.append(("user", base_query))

            # 5. Gọi LLM Provider Streaming và thu thập câu trả lời
            logger.info("[CHAT] Calling LLM streaming for query='%s', history_count=%d...", base_query, len(history))
            full_response_chunks = []

            async for chunk in self.llm_provider.astream(messages_for_llm):
                if request and await request.is_disconnected():
                    return
                token_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token_text:
                    full_response_chunks.append(token_text)
                    yield f"event: token\ndata: {json.dumps({'text': token_text}, ensure_ascii=False)}\n\n"

            # 6. Lưu câu trả lời hoàn chỉnh vào DB sau khi stream xong
            if request and await request.is_disconnected():
                return

            if conversation_id and full_response_chunks:
                full_response = "".join(full_response_chunks)
                self.chat_repo.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response,
                )
                self.chat_repo.touch_conversation(conversation_id)

            yield "event: chat_ended\ndata: {}\n\n"

        except asyncio.CancelledError:
            # The ASGI server cancels the generator when the downstream client disconnects.
            logger.info("[CHAT] Stream cancelled by client for conversation_id=%s", conversation_id)
            raise
        except Exception as ex:
            error_msg = json.dumps({'text': '\n[Lỗi kết nối tới mô hình AI hoặc Database]'})
            yield f"event: token\ndata: {error_msg}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"
