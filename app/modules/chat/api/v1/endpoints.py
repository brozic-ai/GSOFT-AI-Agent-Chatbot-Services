"""
API Router cho phân hệ Chatbot RAG (Chat Stream SSE Endpoints).
Dành riêng cho phân hệ Chatbot RAG theo chuẩn Clean Architecture & DDD.
"""

import logging

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.modules.chat.api.v1.schemas import ChatRequest
from app.modules.chat.service import ChatService
from app.routers.dependencies import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_user_roles: str | None = Header(None, alias="X-User-Roles"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Endpoint RAG Chat Streaming bằng Server-Sent Events (SSE).
    Nhận danh sách vai trò từ Body hoặc Header `X-User-Roles` từ C# Gateway để thực thi RBAC Vector Search.
    """
    roles = request.user_roles or x_user_roles
    logger.info(
        "[CHAT] Received POST /stream request | query='%s' | roles='%s'",
        request.message,
        roles,
    )

    generator = service.generate_rag_response_stream(
        message=request.message,
        user_roles=roles,
    )

    return StreamingResponse(generator, media_type="text/event-stream")
