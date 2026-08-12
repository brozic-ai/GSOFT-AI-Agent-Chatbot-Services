"""
Service tầng nghiệp vụ Chatbot RAG (Chat Business Service).
Điều phối truy vấn ngữ cảnh RAG có phân quyền (User Roles & Department RBAC),
quản lý lịch sử hội thoại (Chat History) và gọi LLM Streaming.
"""

import json
import logging
import uuid
from typing import AsyncGenerator, Optional, List, Dict, Any
from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.rag.context.builder import RagContextBuilder, determine_max_tokens
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.core.config import settings
from app.modules.chat.repository import ChatRepository

logger = logging.getLogger(__name__)


class ChatService:
    """Service xử lý phản hồi câu hỏi RAG với phân quyền RBAC và quản lý Lịch sử hội thoại."""

    def __init__(
        self,
        retriever: VectorRetriever,
        llm_provider: BaseChatModel,
        chat_repository: ChatRepository,
    ):
        self.retriever = retriever
        self.llm_provider = llm_provider
        self.chat_repository = chat_repository

    async def generate_rag_response_stream(
        self,
        message: str,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Tạo luồng Server-Sent Events (SSE) phản hồi câu hỏi RAG.
        Đảm bảo lọc tài liệu theo vai trò (user_roles) và Phòng ban (user_department),
        đồng thời tự động lưu trữ Lịch sử hội thoại vào CSDL SQL Server.
        """
        # 1. Xác định/Khởi tạo conversation_id (Memory-only step)
        if not conversation_id or not conversation_id.strip():
            conversation_id = str(uuid.uuid4())

        base_query = message.strip()

        try:
            # 2. Phát ngay lập tức sự kiện khởi đầu chat kèm conversation_id cho FE (trước mọi DB operation)
            start_payload = json.dumps({"conversation_id": conversation_id})
            yield f"event: chat_started\ndata: {start_payload}\n\n"

            # 3. Tạo/Cập nhật thông tin Phiên hội thoại và lưu câu hỏi của User vào DB
            self.chat_repository.get_or_create_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                user_roles=user_roles,
                user_department=user_department,
                title=base_query[:100] if base_query else "Hội thoại mới",
            )
            if base_query:
                self.chat_repository.save_message(conversation_id, role="user", content=base_query)

            # 4. Kiểm tra luồng Early Return: Câu hỏi rỗng
            if not base_query:
                reply_empty = "Bạn chưa nhập câu hỏi."
                self.chat_repository.save_message(conversation_id, role="assistant", content=reply_empty)
                yield f"event: token\ndata: {json.dumps({'text': reply_empty}, ensure_ascii=False)}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 5. Kiểm tra luồng Early Return: Lời chào đơn giản
            if base_query.lower() in ["hi", "hello", "xin chào", "chào", "alo"]:
                greeting = "Xin chào! Tôi là trợ lý AI thông minh. Tôi có thể giúp gì cho bạn?"
                self.chat_repository.save_message(conversation_id, role="assistant", content=greeting)
                yield "event: citations\ndata: []\n\n"
                yield f"event: token\ndata: {json.dumps({'text': greeting}, ensure_ascii=False)}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 6. Truy vấn ngữ cảnh RAG từ Vector Store với phân quyền RBAC Vai trò + Phòng ban
            thinking_search_json = json.dumps({'text': 'Đang truy vấn ngữ cảnh tài liệu theo phân quyền...\n'}, ensure_ascii=False)
            yield f"event: thinking\ndata: {thinking_search_json}\n\n"

            search_res = await self.retriever.retrieve_context(
                query=base_query,
                top_k=top_k,
                user_roles=user_roles,
                user_department=user_department,
            )

            raw_documents = search_res["documents"][0] if search_res.get("documents") else []
            raw_metadatas = search_res["metadatas"][0] if search_res.get("metadatas") else []

            # 7. Xây dựng Ngữ cảnh RAG đã qua làm sạch, khử trùng lặp và giới hạn dung lượng
            context_str, used_metadatas, used_citations = RagContextBuilder.build(
                documents=raw_documents, metadatas=raw_metadatas
            )
            citations_json = json.dumps(used_citations, ensure_ascii=False, default=str)

            # 8. Trả về trích dẫn tài liệu chuẩn xác thực sự dùng trong prompt (Citations SSE Event)
            yield f"event: citations\ndata: {citations_json}\n\n"

            # 9. Kiểm tra luồng Early Return: Không tìm thấy tài liệu phù hợp sau khi lọc
            if not context_str or not context_str.strip():
                no_doc_msg = "Tôi không tìm thấy thông tin phù hợp trong tài liệu được cấp quyền."
                self.chat_repository.save_message(
                    conversation_id, role="assistant", content=no_doc_msg, citations_json=citations_json
                )
                no_doc_json = json.dumps({'text': no_doc_msg}, ensure_ascii=False)
                yield f"event: token\ndata: {no_doc_json}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            thinking_extract_text = f"Đã trích xuất {len(used_citations)} trích dẫn tài liệu phù hợp.\nĐang suy luận và tổng hợp câu trả lời...\n\n"
            thinking_extract_json = json.dumps({'text': thinking_extract_text}, ensure_ascii=False)
            yield f"event: thinking\ndata: {thinking_extract_json}\n\n"

            # 10. Lấy lịch sử hội thoại cũ (loại bỏ tin nhắn câu hỏi vừa lưu ở bước 3 khỏi history cũ)
            raw_history = self.chat_repository.get_chat_history(
                conversation_id, limit=settings.CHAT_HISTORY_LIMIT + 1
            )
            if raw_history and raw_history[-1]["role"] == "user" and raw_history[-1]["content"] == base_query:
                history_msgs = raw_history[:-1]
            else:
                history_msgs = raw_history

            # 11. Xây dựng Danh sách Messages gửi cho LLM Streaming
            system_prompt = (
                "Bạn là trợ lý AI thông minh của hệ thống Enterprise. "
                "Hãy trả lời câu hỏi của người dùng dựa trên NGỮ CẢNH TÀI LIỆU được cung cấp bên dưới.\n"
                "Quy tắc:\n"
                "1. Chỉ sử dụng thông tin trong phần NGỮ CẢNH TÀI LIỆU. Không tự suy diễn.\n"
                "2. Nếu tài liệu không có thông tin, hãy trả lời: 'Tôi không tìm thấy thông tin này trong tài liệu.'\n"
                "3. Trả lời ngắn gọn, trực tiếp, tự nhiên bằng tiếng Việt."
            )

            llm_messages = [("system", system_prompt)]

            for h in history_msgs:
                llm_messages.append((h["role"], h["content"]))

            # Đính kèm câu hỏi mới nhất kèm Ngữ cảnh RAG
            user_prompt = f"NGỮ CẢNH TÀI LIỆU:\n{context_str}\n\nCÂU HỎI: {base_query}"
            llm_messages.append(("user", user_prompt))

            # 12. Gắn max_tokens động (nếu bật) và Gọi LLM Provider Streaming
            llm_engine = self.llm_provider
            if getattr(settings, "RAG_DYNAMIC_MAX_TOKENS_ENABLED", True) and context_str:
                calc_max_tokens = determine_max_tokens(context_str)
                try:
                    llm_engine = self.llm_provider.bind(max_tokens=calc_max_tokens)
                except Exception:
                    try:
                        llm_engine = self.llm_provider.bind(max_output_tokens=calc_max_tokens)
                    except Exception as bind_ex:
                        logger.warning("[CHAT] Could not bind dynamic max_tokens (%s); using default provider.", bind_ex)

            logger.info("[CHAT] Calling LLM streaming for query='%s', history_count=%d...", base_query, len(history_msgs))
            full_response_text = ""
            in_thinking = False

            async for chunk in llm_engine.astream(llm_messages):
                token_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if not token_text:
                    continue

                full_response_text += token_text

                # Parse <think> and </think> tags from LLM stream (e.g. Qwen2.5 / DeepSeek R1)
                if "<think>" in token_text:
                    in_thinking = True
                    parts = token_text.split("<think>")
                    if parts[0]:
                        yield f"event: token\ndata: {json.dumps({'text': parts[0]}, ensure_ascii=False)}\n\n"
                    if len(parts) > 1 and parts[1]:
                        if "</think>" in parts[1]:
                            think_parts = parts[1].split("</think>")
                            yield f"event: thinking\ndata: {json.dumps({'text': think_parts[0]}, ensure_ascii=False)}\n\n"
                            in_thinking = False
                            if think_parts[1]:
                                yield f"event: token\ndata: {json.dumps({'text': think_parts[1]}, ensure_ascii=False)}\n\n"
                        else:
                            yield f"event: thinking\ndata: {json.dumps({'text': parts[1]}, ensure_ascii=False)}\n\n"
                    continue

                if in_thinking:
                    if "</think>" in token_text:
                        parts = token_text.split("</think>")
                        if parts[0]:
                            yield f"event: thinking\ndata: {json.dumps({'text': parts[0]}, ensure_ascii=False)}\n\n"
                        in_thinking = False
                        if len(parts) > 1 and parts[1]:
                            yield f"event: token\ndata: {json.dumps({'text': parts[1]}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"event: thinking\ndata: {json.dumps({'text': token_text}, ensure_ascii=False)}\n\n"
                else:
                    yield f"event: token\ndata: {json.dumps({'text': token_text}, ensure_ascii=False)}\n\n"

            # 13. Lưu câu trả lời hoàn chỉnh của Assistant + Citations vào CSDL SQL Server
            if full_response_text:
                self.chat_repository.save_message(
                    conversation_id, role="assistant", content=full_response_text, citations_json=citations_json
                )

            yield "event: chat_ended\ndata: {}\n\n"

        except Exception as ex:
            logger.error("[FAIL] Error in RAG Chat Stream: %s", ex, exc_info=True)
            err_text = "\n[Lỗi kết nối tới mô hình AI hoặc Database]"
            try:
                self.chat_repository.save_message(conversation_id, role="assistant", content=err_text)
            except Exception as save_ex:
                logger.warning("[WARN] Failed to save exception response to DB: %s", save_ex)

            err_json = json.dumps({"text": err_text})
            yield f"event: token\ndata: {err_json}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"

    def list_conversations(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các phiên trò chuyện."""
        return self.chat_repository.list_conversations(user_id=user_id, limit=limit)

    def get_conversation_messages(self, conversation_id: str, requesting_user_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Lấy chi tiết tin nhắn của 1 phiên trò chuyện."""
        return self.chat_repository.get_conversation_messages(conversation_id=conversation_id, requesting_user_id=requesting_user_id)

    def delete_conversation(self, conversation_id: str, requesting_user_id: Optional[str] = None) -> bool:
        """Xóa 1 phiên trò chuyện."""
        return self.chat_repository.delete_conversation(conversation_id=conversation_id, requesting_user_id=requesting_user_id)
