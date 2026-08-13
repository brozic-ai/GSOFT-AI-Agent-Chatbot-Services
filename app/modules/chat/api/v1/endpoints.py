"""
API Router cho phân hệ Chatbot RAG (Chat Stream SSE Endpoints + Conversation History).
Dành riêng cho phân hệ Chatbot RAG theo chuẩn Clean Architecture & DDD.

Endpoints:
  POST   /stream                          — RAG Chat SSE Streaming (kèm lịch sử)
  POST   /conversations                   — Tạo phiên hội thoại mới
  GET    /conversations                   — Lấy danh sách phiên của user
  DELETE /conversations/{id}              — Xóa phiên hội thoại
  GET    /conversations/{id}/messages     — Lấy chi tiết lịch sử tin nhắn
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.modules.chat.api.v1.schemas import (
    ChatRequest,
    ConversationCreateResponse,
    ConversationResponse,
    ChatMessageResponse,
    ConversationUpdateRequest,
)
from app.modules.chat.service import ChatService
from app.routers.dependencies import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Conversation Management Endpoints ──

@router.post("/conversations", response_model=ConversationCreateResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    x_user_id: str = Header(..., alias="X-User-Id"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Tạo phiên hội thoại mới.
    Front-end gọi endpoint này khi reload ứng dụng hoặc khi người dùng bấm 'New Chat'.
    Trả về `conversation_id` để dùng trong các request chat tiếp theo.
    """
    try:
        conv_id = service.create_conversation(user_id=x_user_id, title="\u0110o\u1ea1n chat m\u1edbi")
        return ConversationCreateResponse(
            conversation_id=conv_id,
            title="\u0110o\u1ea1n chat m\u1edbi",
        )
    except Exception as ex:
        logger.error("[FAIL] Error creating conversation for user='%s': %s", x_user_id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.get("/conversations", response_model=List[ConversationResponse])
def list_conversations(
    x_user_id: str = Header(..., alias="X-User-Id"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: ChatService = Depends(get_chat_service),
):
    """
    Lấy danh sách tất cả phiên hội thoại của người dùng (dùng để hiển thị Sidebar lịch sử).
    Sắp xếp theo thứ tự mới nhất trước (updated_at DESC).
    """
    try:
        return service.list_conversations(user_id=x_user_id, limit=limit, offset=offset)
    except Exception as ex:
        logger.error("[FAIL] Error listing conversations for user='%s': %s", x_user_id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int,
    request: ConversationUpdateRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    service: ChatService = Depends(get_chat_service),
):
    """Rename and/or pin a conversation owned by the current user."""
    if request.title is None and request.is_pinned is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cần truyền title hoặc is_pinned.")
    try:
        result = service.update_conversation(
            conversation_id=conversation_id,
            user_id=x_user_id,
            title=request.title,
            is_pinned=request.is_pinned,
        )
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phiên chat không tồn tại hoặc không thuộc user.")
        return result
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    x_user_id: str = Header(..., alias="X-User-Id"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Xóa phiên hội thoại và toàn bộ tin nhắn liên quan.
    Kiểm tra quyền sở hữu: chỉ người tạo phiên mới được xóa.
    """
    deleted = service.delete_conversation(conversation_id=conversation_id, user_id=x_user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation ID={conversation_id} không tồn tại hoặc bạn không có quyền truy cập.",
        )


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessageResponse])
def get_messages(
    conversation_id: int,
    x_user_id: str = Header(..., alias="X-User-Id"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Lấy toàn bộ lịch sử tin nhắn của một phiên hội thoại.
    Kiểm tra quyền sở hữu trước khi trả về dữ liệu.
    """
    # Kiểm tra quyền sở hữu conversation
    conv = service.get_conversation(conversation_id=conversation_id, user_id=x_user_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation ID={conversation_id} không tồn tại hoặc bạn không có quyền truy cập.",
        )
    try:
        # Lấy toàn bộ tin nhắn (limit=1000 cho trang xem lại lịch sử)
        return service.get_chat_history(conversation_id=conversation_id, limit=1000)
    except Exception as ex:
        logger.error("[FAIL] Error fetching messages for conversation_id=%d: %s", conversation_id, ex, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(ex))


# ── RAG Chat Streaming Endpoint ──

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Endpoint RAG Chat Streaming bằng Server-Sent Events (SSE).

    - Nhận `conversation_id` trong body để load/lưu lịch sử hội thoại.
    - Nhận vai trò từ Body hoặc Header `X-User-Roles` để thực thi RBAC Vector Search.
    - Nếu không có `conversation_id`, bot vẫn hoạt động nhưng không lưu lịch sử.
    """
    # Kiểm tra quyền sở hữu conversation nếu có truyền conversation_id
    if request.conversation_id and x_user_id:
        conv = service.get_conversation(
            conversation_id=request.conversation_id,
            user_id=x_user_id,
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Conversation ID={request.conversation_id} không tồn tại hoặc bạn không có quyền truy cập.",
            )

    roles = request.user_roles or x_user_roles

    generator = service.generate_rag_response_stream(
        message=request.message,
        conversation_id=request.conversation_id,
        user_id=x_user_id,
        user_roles=roles,
        request=http_request,
    )

    return StreamingResponse(generator, media_type="text/event-stream")
