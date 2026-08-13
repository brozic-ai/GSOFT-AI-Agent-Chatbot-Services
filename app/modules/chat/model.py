"""
SQLAlchemy ORM Models cho phân hệ Lịch sử Trò chuyện (Chat History).
Quản lý 2 bảng: Conversations (phiên hội thoại) và ChatMessages (từng tin nhắn).

Bảng sẽ được tạo tự động khi startup thông qua Base.metadata.create_all() trong init_db().
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Column, Integer, String, Text, DateTime, ForeignKey, Index, Unicode, UnicodeText
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    """Bảng lưu phiên hội thoại của người dùng (Chat Session)."""
    __tablename__ = "Conversations"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    user_id = Column("UserId", Unicode(200), nullable=False, index=True)
    is_pinned = Column("IsPinned", Boolean, nullable=False, default=False, server_default="0")
    pinned_at = Column("PinnedAt", DateTime, nullable=True)
    title_source = Column("TitleSource", String(20), nullable=False, default="default", server_default="default")
    title = Column("Title", Unicode(255), nullable=False, default="Cuộc hội thoại mới")
    created_at = Column("CreatedAt", DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column("UpdatedAt", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Quan hệ 1-N tới danh sách tin nhắn trong phiên này
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Bảng lưu từng tin nhắn trong phiên hội thoại (User & Assistant Messages)."""
    __tablename__ = "ChatMessages"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        "ConversationId", Integer,
        ForeignKey("Conversations.Id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column("Role", String(20), nullable=False)   # 'user' | 'assistant' | 'system'
    content = Column("Content", UnicodeText, nullable=False)
    created_at = Column("CreatedAt", DateTime, nullable=False, default=datetime.utcnow)

    # Quan hệ N-1 ngược lại tới phiên hội thoại cha
    conversation = relationship("Conversation", back_populates="messages")


# Đánh chỉ mục Index bổ sung
Index("IX_Conversations_UserId", Conversation.user_id)
Index("IX_Conversations_User_Pinned_Updated", Conversation.user_id, Conversation.is_pinned, Conversation.updated_at)
Index("IX_ChatMessages_ConversationId", ChatMessage.conversation_id)
