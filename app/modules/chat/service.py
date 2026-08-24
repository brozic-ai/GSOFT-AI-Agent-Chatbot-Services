"""
Service tầng nghiệp vụ Chatbot RAG (Chat Business Service).
Điều phối truy vấn ngữ cảnh RAG có phân quyền (User Roles RBAC), xây dựng Prompt,
gọi LLM Streaming và quản lý lịch sử hội thoại (Chat History).
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Optional, List, Dict, Any, Union
from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.rag.context.builder import RagContextBuilder, determine_max_tokens
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

    def create_conversation(self, user_id: str, title: str = "Đoạn chat mới") -> int:
        """Tạo phiên hội thoại mới. Trả về conversation_id (int)."""
        return self.chat_repo.create_conversation(user_id=user_id, title=title)

    def get_conversation(self, conversation_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin phiên hội thoại, kiểm tra quyền sở hữu theo user_id."""
        return self.chat_repo.get_conversation(conversation_id=conversation_id, user_id=user_id)

    def list_conversations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lấy danh sách lịch sử các phiên hội thoại của người dùng."""
        return self.chat_repo.list_conversations(user_id=user_id, limit=limit, offset=offset)

    def update_conversation(
        self,
        conversation_id: int,
        user_id: str,
        title: Optional[str] = None,
        is_pinned: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        if title is not None and not title.strip():
            raise ValueError("Title không được để trống.")
        return self.chat_repo.update_conversation(conversation_id, user_id, title, is_pinned)

    async def generate_conversation_title(self, conversation_id: int, question: str) -> None:
        """Generate a short title; title generation failure must not fail the chat."""
        fallback = question.strip()[:80]
        try:
            from app.llmops.langfuse import get_langfuse_langchain_config

            title_config = get_langfuse_langchain_config(
                session_id=str(conversation_id),
                tags=["title-generation", "background"],
                trace_name=f"Generate-Title: cid={conversation_id}",
            )

            response = await asyncio.wait_for(
                self.llm_provider.ainvoke(
                    [
                        ("system", "Create a concise Vietnamese chat title, 3-8 words, no quotes or markdown."),
                        ("user", question.strip()),
                    ],
                    config=title_config,
                ),
                timeout=5,
            )
            title = response.content if hasattr(response, "content") else str(response)
            if isinstance(title, list):
                title = "".join(str(item) for item in title)
            title = str(title).strip().strip("\"'")[:80]
            self.chat_repo.update_conversation_title(conversation_id, title or fallback, source="llm")
        except Exception as ex:
            logger.warning("[WARN] Could not generate title for conversation_id=%s: %s", conversation_id, ex)
            self.chat_repo.update_conversation_title(conversation_id, fallback, source="llm")

    def get_chat_history(self, conversation_id: int, limit: int = HISTORY_LIMIT) -> List[Dict[str, Any]]:
        """Lấy N tin nhắn gần nhất trong phiên hội thoại."""
        return self.chat_repo.get_chat_history(conversation_id=conversation_id, limit=limit)

    def delete_conversation(self, conversation_id: int, user_id: str) -> bool:
        """Xóa phiên hội thoại và toàn bộ tin nhắn liên quan."""
        return self.chat_repo.delete_conversation(conversation_id=conversation_id, user_id=user_id)

    # ── RAG Streaming ──

    async def generate_rag_response_stream(
        self,
        message: str = "",
        conversation_id: Optional[int] = None,
        user_id: Optional[str] = "guest",
        user_roles: Optional[Union[List[str], str]] = None,
        user_department: Optional[str] = None,
        top_k: int = 5,
        images: Optional[List[Dict[str, Any]]] = None,
        request: Optional[Any] = None,
        question: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Tạo luồng Server-Sent Events (SSE) phản hồi qua Master Orchestrator Graph.

        Luồng xử lý Enterprise Multi-Agent:
        1. Lấy lịch sử tin nhắn từ DB (nếu có conversation_id).
        2. Lưu câu hỏi mới của User vào DB và tạo tiêu đề tự động nếu là tin nhắn đầu tiên.
        3. Khởi tạo OrchestratorState kèm messages và user_info (roles, department, user_id).
        4. Thực thi Master Orchestrator Graph:
           - Input Guardrail (Chặn tấn công)
           - Supervisor Intent Classifier (RAG, Procurement, FAQ, Fallback)
           - Sub-Agent tương ứng (RAG Knowledge Agent 4-Node, gAMSPro ReAct, FAQ, Fallback)
           - Output Guardrail (Kiểm duyệt an toàn thông tin)
        5. Trả về trích dẫn citations (nếu có từ RAG) và stream token về Frontend qua SSE.
        6. Lưu phản hồi của Assistant vào DB.
        """
        try:
            # Phát sự kiện khởi đầu chat
            yield "event: chat_started\ndata: {}\n\n"

            if request and await request.is_disconnected():
                return

            base_query = (message or question or "").strip()
            if not base_query:
                reply_empty = "Bạn chưa nhập câu hỏi."
                if conversation_id:
                    self.chat_repo.save_message(
                        conversation_id=conversation_id, role="assistant", content=reply_empty
                    )
                yield f"event: token\ndata: {json.dumps({'text': reply_empty}, ensure_ascii=False)}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # 1. Lấy lịch sử hội thoại từ DB
            history: List[Dict[str, Any]] = []
            is_first_message = True
            if conversation_id:
                if request and await request.is_disconnected():
                    return
                message_count = self.chat_repo.get_message_count(conversation_id)
                is_first_message = message_count == 0
                if message_count > 0:
                    history = self.chat_repo.get_chat_history(
                        conversation_id=conversation_id, limit=HISTORY_LIMIT
                    )

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
                    asyncio.create_task(
                        self.generate_conversation_title(
                            conversation_id, base_query
                        )
                    )

            # 3. Chuẩn bị danh sách BaseMessage cho Master Orchestrator
            from langchain_core.messages import AIMessage, HumanMessage

            messages_for_graph = []
            for hist_msg in history:
                role = hist_msg.get("role")
                content = hist_msg.get("content", "")
                if role in ("user", "human"):
                    messages_for_graph.append(HumanMessage(content=content))
                elif role in ("assistant", "ai"):
                    messages_for_graph.append(AIMessage(content=content))
            messages_for_graph.append(HumanMessage(content=base_query))

            # 4. Thiết lập Tracing Langfuse / LangSmith
            from app.ai.orchestration.graph import orchestrator_graph
            from app.core.config import settings
            from app.llmops.langfuse import get_langfuse_langchain_config

            stream_config = get_langfuse_langchain_config(
                user_id=user_id,
                session_id=str(conversation_id) if conversation_id else None,
                tags=[
                    "orchestrator",
                    "chat",
                    "multi-agent",
                    getattr(settings, "AI_PROVIDER", "llm"),
                ],
                metadata={
                    "conversation_id": str(conversation_id) if conversation_id else None,
                    "user_roles": user_roles,
                    "user_department": user_department,
                    "top_k": top_k,
                },
                trace_name=f"Orchestrator-Chat: {base_query[:35]}",
            )

            state_input = {
                "session_id": str(conversation_id)
                if conversation_id
                else f"chat-{uuid.uuid4().hex[:8]}",
                "user_query": base_query,
                "user_info": {
                    "roles": user_roles,
                    "department": user_department,
                    "user_id": user_id,
                },
                "chat_history": history,
                "messages": messages_for_graph,
            }

            # 5. Thực thi Master Orchestrator Graph
            logger.info(
                "[CHAT] Invoking Master Orchestrator for query='%s', history_count=%d...",
                base_query,
                len(history),
            )
            orch_result = await orchestrator_graph.ainvoke(
                state_input, config=stream_config
            )

            if request and await request.is_disconnected():
                return

            agent_output = (
                orch_result.get("agent_output")
                or "Tôi không thể xử lý yêu cầu lúc này."
            )
            citations_list = orch_result.get("citations") or []

            # 6. Phát sự kiện trích dẫn tài liệu (Citations SSE Event)
            yield f"event: citations\ndata: {json.dumps(citations_list, ensure_ascii=False, default=str)}\n\n"

            # 7. Stream từng token/chunk tới Frontend với hiệu ứng typing animation mượt mà
            chunk_size = 6
            for i in range(0, len(agent_output), chunk_size):
                if request and await request.is_disconnected():
                    return
                chunk = agent_output[i : i + chunk_size]
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.015)

            # 8. Lưu câu trả lời hoàn chỉnh vào DB sau khi hoàn tất
            if request and await request.is_disconnected():
                return

            if conversation_id and agent_output:
                self.chat_repo.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=agent_output,
                )
                self.chat_repo.touch_conversation(conversation_id)

            yield "event: chat_ended\ndata: {}\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            # ASGI server / anyio cancels the generator when the client disconnects or clicks Cancel stream.
            logger.info(
                "[CHAT] Stream closed/cancelled by client for conversation_id=%s",
                conversation_id,
            )
            return

        except Exception as ex:
            logger.error(
                "[CHAT] Stream error for conversation_id=%s: %s",
                conversation_id,
                ex,
                exc_info=True,
            )
            error_msg = json.dumps(
                {
                    "text": "\n⚠️ Hệ thống đang gặp sự cố kết nối. Vui lòng thử lại sau."
                },
                ensure_ascii=False,
            )
            yield f"event: token\ndata: {error_msg}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"
        finally:
            from app.llmops.langfuse import flush_langfuse

            flush_langfuse()




