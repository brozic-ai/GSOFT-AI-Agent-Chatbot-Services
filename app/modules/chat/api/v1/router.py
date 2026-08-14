"""
Router module cho phân hệ Chatbot RAG (v1).
Re-export router từ endpoints.py chuẩn DDD.
"""

from app.modules.chat.api.v1.endpoints import router

__all__ = ["router"]
