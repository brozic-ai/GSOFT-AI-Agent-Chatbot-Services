"""
API Router cho phân hệ Chatbot RAG (Chat Stream SSE Endpoints & Conversations Management).
Dành riêng cho phân hệ Chatbot RAG theo chuẩn Clean Architecture & DDD.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.modules.chat.api.v1.schemas import (
    ChatRequest, ConversationResponse, ConversationListResponse, ChatMessageResponse
)
from app.modules.chat.service import ChatService
from app.routers.dependencies import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    x_user_department: Optional[str] = Header(None, alias="X-User-Department"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    service: ChatService = Depends(get_chat_service),
):
    """
    Endpoint RAG Chat Streaming bằng Server-Sent Events (SSE).
    Nhận danh sách vai trò từ Body/Header `X-User-Roles`, Phòng ban từ `X-User-Department`,
    và User ID từ Body/Header `X-User-Id` để lưu vết lịch sử trò chuyện (Chat History).
    """
    roles = request.user_roles or x_user_roles
    department = request.user_department or x_user_department
    user_id = request.user_id or x_user_id

    generator = service.generate_rag_response_stream(
        message=request.message,
        user_roles=roles,
        user_department=department,
        conversation_id=request.conversation_id,
        user_id=user_id,
    )

    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    user_id: Optional[str] = Query(None),
    service: ChatService = Depends(get_chat_service),
):
    """
    Lấy danh sách tất cả các phiên trò chuyện của người dùng (sắp xếp phiên mới nhất lên trước).
    """
    target_user_id = x_user_id or user_id
    items = service.list_conversations(user_id=target_user_id, limit=limit)
    return ConversationListResponse(
        items=[ConversationResponse(**item) for item in items],
        total_count=len(items)
    )


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    user_id: Optional[str] = Query(None),
    service: ChatService = Depends(get_chat_service),
):
    """
    Lấy toàn bộ lịch sử tin nhắn của một phiên trò chuyện cụ thể.
    """
    target_user_id = x_user_id or user_id
    messages = service.get_conversation_messages(conversation_id=conversation_id, requesting_user_id=target_user_id)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phiên trò chuyện ID '{conversation_id}' không tồn tại hoặc bạn không có quyền truy cập."
        )
    return [ChatMessageResponse(**msg) for msg in messages]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    user_id: Optional[str] = Query(None),
    service: ChatService = Depends(get_chat_service),
):
    """
    Xóa 1 phiên trò chuyện và toàn bộ tin nhắn thuộc phiên đó.
    """
    target_user_id = x_user_id or user_id
    success = service.delete_conversation(conversation_id=conversation_id, requesting_user_id=target_user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phiên trò chuyện ID '{conversation_id}' không tồn tại hoặc bạn không có quyền xóa."
        )
    return {"status": "success", "message": f"Đã xóa phiên trò chuyện ID '{conversation_id}' thành công."}
