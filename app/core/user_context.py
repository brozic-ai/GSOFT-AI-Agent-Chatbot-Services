"""
Module quản lý Ngữ cảnh Người dùng (User Context) xuyên suốt request lifecycle.
Sử dụng ContextVars chuẩn của Python/ASGI, đảm bảo an toàn tuyệt đối khi xử lý đồng thời (Thread-safe / Async-safe).
"""

from contextvars import ContextVar
from typing import Optional

from app.core.config import settings

# Khởi tạo ContextVars cho từng thuộc tính của phiên người dùng
_CURRENT_USER_NAME: ContextVar[Optional[str]] = ContextVar("current_user_name", default=None)
_CURRENT_USER_ID: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)
_CURRENT_AUTH_TOKEN: ContextVar[Optional[str]] = ContextVar("current_auth_token", default=None)
_CURRENT_USER_ROLES: ContextVar[Optional[str]] = ContextVar("current_user_roles", default=None)
_CURRENT_USER_DEPARTMENT: ContextVar[Optional[str]] = ContextVar("current_user_department", default=None)


from urllib.parse import unquote


def _safe_unquote(val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    try:
        return unquote(val).strip()
    except Exception:
        return val.strip()


def set_user_context(
    user_name: Optional[str] = None,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    roles: Optional[str] = None,
    department: Optional[str] = None,
) -> None:
    """Thiết lập ngữ cảnh người dùng cho request/coroutine hiện tại."""
    clean_uname = _safe_unquote(user_name)
    clean_uid = _safe_unquote(user_id)
    clean_roles = _safe_unquote(roles)
    clean_dept = _safe_unquote(department)
    
    clean_token = auth_token.strip() if auth_token and auth_token.strip() else None
    if clean_token and clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    _CURRENT_USER_NAME.set(clean_uname if clean_uname else None)
    _CURRENT_USER_ID.set(clean_uid if clean_uid else None)
    _CURRENT_AUTH_TOKEN.set(clean_token)
    _CURRENT_USER_ROLES.set(clean_roles if clean_roles else None)
    _CURRENT_USER_DEPARTMENT.set(clean_dept if clean_dept else None)


def get_current_user_name() -> Optional[str]:
    """Lấy username của người dùng đang thực hiện request (nếu có)."""
    return _CURRENT_USER_NAME.get()


def get_current_user_id() -> Optional[str]:
    """Lấy user_id của người dùng đang thực hiện request (nếu có)."""
    return _CURRENT_USER_ID.get()


def get_current_auth_token() -> Optional[str]:
    """Lấy Bearer JWT token từ phiên của người dùng (nếu có)."""
    return _CURRENT_AUTH_TOKEN.get()


def get_resolved_user_name(explicit_user: Optional[str] = None) -> Optional[str]:
    """
    Giải quyết username chuẩn theo thứ tự ưu tiên:
    1. Tham số do người dùng chỉ định rõ (bỏ qua các giá trị placeholder như 'auto', 'none', 'null')
    2. Username lấy từ phiên đăng nhập thực tế của người dùng hiện tại (ContextVar)
    3. Tuyệt đối không fallback về bất kỳ user mặc định nào (trả về None nếu chưa xác thực).
    """
    if explicit_user and explicit_user.strip():
        val = explicit_user.strip()
        # Bỏ qua nếu LLM sinh ra các từ khóa giả định / placeholder
        if val.lower() not in ("auto", "none", "null", "undefined", "current", "current_user", "me", "toi"):
            return val

    ctx_user = get_current_user_name()
    if ctx_user and ctx_user.strip():
        return ctx_user.strip()

    return None


def require_current_user_name() -> Optional[str]:
    """Lấy username bắt buộc của phiên đăng nhập hiện tại."""
    ctx_user = get_current_user_name()
    if ctx_user and ctx_user.strip():
        return ctx_user.strip()
    return None



def reset_user_context() -> None:
    """Khởi tạo lại ngữ cảnh người dùng về giá trị rỗng."""
    _CURRENT_USER_NAME.set(None)
    _CURRENT_USER_ID.set(None)
    _CURRENT_AUTH_TOKEN.set(None)
    _CURRENT_USER_ROLES.set(None)
    _CURRENT_USER_DEPARTMENT.set(None)
