"""
SQLAlchemy ORM Models cho phân hệ Chatbot RAG (Conversations & Chat Messages History).
Lưu trữ phiên hội thoại và lịch sử tin nhắn trò chuyện trên CSDL SQL Server (dbo.Conversations & dbo.ChatMessages).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Index, Unicode, UnicodeText
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    """Bảng lưu thông tin phiên trò chuyện RAG."""
    __tablename__ = "Conversations"

    id = Column("Id", Unicode(100), primary_key=True)
    user_id = Column("UserId", Unicode(100), nullable=True)
    user_roles = Column("UserRoles", Unicode(500), nullable=True)
    user_department = Column("UserDepartment", Unicode(100), nullable=True)
    title = Column("Title", Unicode(500), nullable=True)
    creation_time = Column("CreationTime", DateTime, nullable=False, default=datetime.utcnow)
    updated_time = Column("UpdatedTime", DateTime, nullable=False, default=datetime.utcnow)

    # Quan hệ 1-N tới danh sách tin nhắn trong phiên (cascade xóa tất cả tin nhắn khi xóa phiên)
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Bảng lưu các tin nhắn đơn lẻ trong phiên trò chuyện RAG (User & Assistant)."""
    __tablename__ = "ChatMessages"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    conversation_id = Column("ConversationId", Unicode(100), ForeignKey("Conversations.Id", ondelete="CASCADE"), nullable=False)
    role = Column("Role", String(20), nullable=False)  # 'user' hoặc 'assistant'
    content = Column("Content", UnicodeText, nullable=False)
    citations = Column("Citations", UnicodeText, nullable=True)  # Chuỗi JSON chứa mảng citations
    creation_time = Column("CreationTime", DateTime, nullable=False, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


# Đánh chỉ mục Index tối ưu tốc độ truy vấn lịch sử tin nhắn
Index("IX_ChatMessages_ConversationId", ChatMessage.conversation_id)
