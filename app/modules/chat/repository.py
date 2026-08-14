"""
Repository Data Access Layer cho phân hệ Lịch sử Trò chuyện (Chat History Repository).
Đóng gói toàn bộ logic truy vấn và ghi dữ liệu vào 2 bảng: Conversations và ChatMessages.

Tuân thủ cùng nguyên tắc SessionLocal với DocumentRepository đang áp dụng trong dự án.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.chat.model import Conversation, ChatMessage

logger = logging.getLogger(__name__)


class ChatRepository:
    """Repository quản lý phiên hội thoại và tin nhắn lịch sử Chat."""

    # ── Conversation Operations ──

    def create_conversation(self, user_id: str, title: str = "Cuộc hội thoại mới") -> str:
        """Tạo phiên hội thoại mới và trả về conversation_id (str)."""
        db: Session = SessionLocal()
        try:
            conv_id = str(uuid.uuid4())
            conv = Conversation(id=conv_id, user_id=user_id, title=title)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            logger.info("[OK] Created Conversation ID=%s for user_id='%s'", conv.id, user_id)
            return conv.id
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error creating Conversation: %s", ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def get_conversation(self, conversation_id: Union[str, int], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin chi tiết của một phiên hội thoại.
        Nếu truyền user_id thì sẽ kiểm tra quyền sở hữu (authorization check).
        """
        db: Session = SessionLocal()
        try:
            query = db.query(Conversation).filter(Conversation.id == str(conversation_id))
            if user_id:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                return None
            return {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            }
        finally:
            db.close()

    @staticmethod
    def _time_label(value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        now = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        seconds = max(0, int((now - value).total_seconds()))
        if seconds < 60:
            return "Vừa xong"
        if seconds < 3600:
            return f"{seconds // 60} phút trước"
        if seconds < 86400:
            return f"{seconds // 3600} giờ trước"
        if seconds < 30 * 86400:
            return f"{seconds // 86400} ngày trước"
        return f"{max(1, seconds // (30 * 86400))} tháng trước"

    @classmethod
    def _serialize_conversation(cls, conv: Conversation) -> Dict[str, Any]:
        def iso(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() + ("Z" if value and value.tzinfo is None else "")

        return {
            "id": conv.id,
            "title": conv.title,
            "is_pinned": bool(conv.is_pinned),
            "created_at": iso(conv.created_at),
            "updated_at": iso(conv.updated_at),
            "time_label": cls._time_label(conv.updated_at),
        }

    def list_conversations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lấy danh sách các phiên hội thoại của người dùng, sắp xếp theo mới nhất trước."""
        db: Session = SessionLocal()
        try:
            convs = (
                db.query(Conversation)
                .filter(Conversation.user_id == user_id)
                .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc(), Conversation.id.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._serialize_conversation(conv) for conv in convs]
        finally:
            db.close()

    def update_conversation_title(self, conversation_id: Union[str, int], title: str, source: str = "llm") -> None:
        """Cập nhật tiêu đề phiên hội thoại (thường dùng từ câu hỏi đầu tiên)."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == str(conversation_id)).first()
            if conv:
                # Giới hạn tiêu đề 80 ký tự
                if source == "llm" and conv.title_source == "manual":
                    return
                conv.title = title[:80] + ("..." if len(title) > 80 else "")
                conv.title_source = source
                conv.updated_at = datetime.utcnow()
                db.commit()
                logger.info("[OK] Updated title for Conversation ID=%s", conversation_id)
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error updating conversation title ID=%s: %s", conversation_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def update_conversation(
        self,
        conversation_id: Union[str, int],
        user_id: str,
        title: Optional[str] = None,
        is_pinned: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(
                Conversation.id == str(conversation_id),
                Conversation.user_id == user_id,
            ).first()
            if not conv:
                return None
            if title is not None:
                conv.title = title.strip()
                conv.title_source = "manual"
            if is_pinned is not None:
                conv.is_pinned = is_pinned
                conv.pinned_at = datetime.utcnow() if is_pinned else None
            conv.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(conv)
            return self._serialize_conversation(conv)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def touch_conversation(self, conversation_id: Union[str, int]) -> None:
        """Cập nhật updated_at của phiên chat để sắp xếp lịch sử chính xác."""
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == str(conversation_id)).first()
            if conv:
                conv.updated_at = datetime.utcnow()
                db.commit()
        except Exception as ex:
            db.rollback()
            logger.warning("[WARN] Could not touch Conversation ID=%s: %s", conversation_id, ex)
        finally:
            db.close()

    def delete_conversation(self, conversation_id: Union[str, int], user_id: str) -> bool:
        """Xóa phiên hội thoại và toàn bộ tin nhắn liên quan (Cascade)."""
        db: Session = SessionLocal()
        try:
            conv = (
                db.query(Conversation)
                .filter(Conversation.id == str(conversation_id), Conversation.user_id == user_id)
                .first()
            )
            if not conv:
                return False
            db.delete(conv)
            db.commit()
            logger.info("[OK] Deleted Conversation ID=%s for user_id='%s'", conversation_id, user_id)
            return True
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error deleting Conversation ID=%s: %s", conversation_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    # ── ChatMessage Operations ──

    def save_message(self, conversation_id: Union[str, int], role: str, content: str) -> int:
        """Lưu một tin nhắn mới vào phiên hội thoại. Trả về message_id."""
        db: Session = SessionLocal()
        try:
            msg = ChatMessage(
                conversation_id=str(conversation_id),
                role=role,
                content=content,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            logger.debug("[OK] Saved message ID=%d (role='%s') for conversation_id=%s", msg.id, role, conversation_id)
            return msg.id
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error saving ChatMessage: %s", ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def get_chat_history(self, conversation_id: Union[str, int], limit: int = 20) -> List[Dict[str, Any]]:
        """
        Lấy N tin nhắn gần nhất trong phiên hội thoại (để làm ngữ cảnh cho LLM).
        Trả về đúng thứ tự thời gian tăng dần (cũ -> mới).
        """
        db: Session = SessionLocal()
        try:
            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == str(conversation_id))
                .order_by(ChatMessage.created_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in msgs
            ]
        finally:
            db.close()

    def get_message_count(self, conversation_id: Union[str, int]) -> int:
        """Đếm số tin nhắn trong phiên hội thoại (dùng để detect tin nhắn đầu tiên)."""
        db: Session = SessionLocal()
        try:
            return db.query(ChatMessage).filter(ChatMessage.conversation_id == str(conversation_id)).count()
        finally:
            db.close()
            db.close()
