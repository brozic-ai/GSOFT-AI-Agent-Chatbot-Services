"""
Repository quản lý dữ liệu Phiên hội thoại và Lịch sử tin nhắn (Chat & Session Repository).
Sử dụng SQLAlchemy ORM (SessionLocal) tuân thủ Clean Architecture.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.chat.model import Conversation, ChatMessage

logger = logging.getLogger(__name__)


class ChatRepository:
    """Repository quản lý CRUD Conversations và ChatMessages trong CSDL SQL Server."""

    def get_or_create_conversation(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lấy phiên hội thoại theo ID, nếu chưa có thì tạo mới."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                conv = Conversation(
                    id=conversation_id,
                    user_id=user_id,
                    user_roles=user_roles,
                    user_department=user_department,
                    title=title or "Hội thoại mới",
                    creation_time=datetime.utcnow(),
                    updated_time=datetime.utcnow(),
                )
                db.add(conv)
                db.commit()
                logger.info("[OK] Created new Conversation ID='%s' for user='%s'", conversation_id, user_id)
            return {
                "id": conv.id,
                "user_id": conv.user_id,
                "user_roles": conv.user_roles,
                "user_department": conv.user_department,
                "title": conv.title,
                "creation_time": conv.creation_time.isoformat() if conv.creation_time else None,
                "updated_time": conv.updated_time.isoformat() if conv.updated_time else None,
            }
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error in get_or_create_conversation ID='%s': %s", conversation_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def list_conversations(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các phiên trò chuyện của user, sắp xếp mới nhất lên đầu."""
        db: Session = SessionLocal()
        try:
            query = db.query(Conversation)
            if user_id:
                query = query.filter(Conversation.user_id == user_id)
            convs = query.order_by(Conversation.updated_time.desc()).limit(limit).all()
            results = []
            for conv in convs:
                results.append({
                    "id": conv.id,
                    "user_id": conv.user_id,
                    "title": conv.title,
                    "creation_time": conv.creation_time.isoformat() if conv.creation_time else None,
                    "updated_time": conv.updated_time.isoformat() if conv.updated_time else None,
                })
            return results
        finally:
            db.close()

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin 1 phiên hội thoại theo ID."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return None
            return {
                "id": conv.id,
                "user_id": conv.user_id,
                "user_roles": conv.user_roles,
                "user_department": conv.user_department,
                "title": conv.title,
                "creation_time": conv.creation_time.isoformat() if conv.creation_time else None,
                "updated_time": conv.updated_time.isoformat() if conv.updated_time else None,
            }
        finally:
            db.close()

    def delete_conversation(self, conversation_id: str, requesting_user_id: Optional[str] = None) -> bool:
        """Xóa phiên trò chuyện kèm tất cả tin nhắn thuộc phiên (Cascade Delete)."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return False

            # Validate ownership nếu requesting_user_id được truyền vào
            if requesting_user_id and conv.user_id and conv.user_id != requesting_user_id:
                logger.warning("[SECURITY] User '%s' attempted to delete Conversation '%s' owned by '%s'",
                               requesting_user_id, conversation_id, conv.user_id)
                return False

            db.delete(conv)
            db.commit()
            logger.info("[OK] Deleted Conversation ID='%s'", conversation_id)
            return True
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error deleting Conversation ID='%s': %s", conversation_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations_json: Optional[str] = None,
    ) -> int:
        """Lưu một tin nhắn mới (user hoặc assistant) và cập nhật UpdatedTime của Conversation."""
        db: Session = SessionLocal()
        try:
            msg = ChatMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                citations=citations_json,
                creation_time=datetime.utcnow(),
            )
            db.add(msg)

            # Cập nhật UpdatedTime của Conversation tương ứng
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                conv.updated_time = datetime.utcnow()

            db.commit()
            logger.debug("[OK] Saved ChatMessage ID=%d, Role='%s' for Conversation='%s'", msg.id, role, conversation_id)
            return msg.id
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error saving ChatMessage for Conversation='%s': %s", conversation_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def get_chat_history(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy N tin nhắn gần nhất của phiên để đính kèm vào RAG LLM Prompt.
        Lấy TOP N tin nhắn mới nhất (DESC) rồi đảo ngược (::-1) về đúng thứ tự thời gian.
        """
        db: Session = SessionLocal()
        try:
            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.id.desc())
                .limit(limit)
                .all()
            )
            # Đảo ngược về thứ tự thời gian từ cũ -> mới
            chronological_msgs = msgs[::-1]
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "citations": msg.citations,
                    "creation_time": msg.creation_time.isoformat() if msg.creation_time else None,
                }
                for msg in chronological_msgs
            ]
        finally:
            db.close()

    def get_conversation_messages(self, conversation_id: str, requesting_user_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Lấy toàn bộ tin nhắn của 1 phiên trò chuyện (cho API xem chi tiết)."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return None

            # Validate ownership nếu requesting_user_id được truyền vào
            if requesting_user_id and conv.user_id and conv.user_id != requesting_user_id:
                logger.warning("[SECURITY] User '%s' attempted to view Conversation '%s' owned by '%s'",
                               requesting_user_id, conversation_id, conv.user_id)
                return None

            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "citations": msg.citations,
                    "creation_time": msg.creation_time.isoformat() if msg.creation_time else None,
                }
                for msg in msgs
            ]
        finally:
            db.close()
