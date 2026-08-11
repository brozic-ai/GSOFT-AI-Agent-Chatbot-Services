"""
Router module cho phân hệ Quản lý Tài liệu (v1).
Re-export router từ endpoints.py chuẩn DDD.
"""

from app.modules.document.api.v1.endpoints import router

__all__ = ["router"]
