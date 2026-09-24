import logging
from typing import Any, Optional
import httpx
from app.core.config import settings
from app.core.user_context import get_current_auth_token

logger = logging.getLogger(__name__)

async def request_backend_api(
    method: str,
    endpoint: str,
    payload: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Gửi HTTP Request (POST / GET) đến backend C# gAMSPro API.
    Chuyển tiếp trực tiếp Bearer Token từ phiên đăng nhập của người dùng (ContextVar).
    Nếu không có token hoặc token hết hạn, báo lỗi yêu cầu đăng nhập (Zero-Admin Architecture).
    """
    token = get_current_auth_token()
    if not token:
        logger.warning(f"No user Bearer token available for request to {endpoint}")
        raise RuntimeError("⚠️ Bạn chưa đăng nhập hoặc phiên làm việc chưa được xác thực. Vui lòng đăng nhập hệ thống gAMSPro để tiếp tục.")

    url = f"{settings.NET_BACKEND_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        req_kwargs: dict[str, Any] = {"headers": headers, "params": params}
        if payload is not None and method.upper() in ("POST", "PUT", "PATCH"):
            req_kwargs["json"] = payload

        res = await client.request(method.upper(), url, **req_kwargs)

        if res.status_code == 401:
            logger.warning(f"User token expired or unauthorized (401) on {endpoint}")
            raise RuntimeError("⚠️ Phiên làm việc của bạn trên gAMSPro đã hết hạn (401 Unauthorized). Vui lòng tải lại trang hoặc đăng nhập lại.")

        if res.status_code != 200:
            logger.error(f"gAMSPro API error on {endpoint} ({res.status_code}): {res.text}")
            raise RuntimeError(f"Lỗi phản hồi từ máy chủ gAMSPro ({res.status_code}): {res.text}")

        data = res.json()
        # Kiểm tra envelope chuẩn của ABP Framework
        if isinstance(data, dict) and data.get("success") is False:
            err_msg = data.get("error", {}).get("message", "Lỗi xử lý từ gAMSPro")
            raise RuntimeError(f"gAMSPro error: {err_msg}")

        return data


async def post_backend_api(
    endpoint: str,
    payload: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Gửi POST request đến backend C# gAMSPro API."""
    return await request_backend_api("POST", endpoint, payload=payload, params=params)


async def get_backend_api(
    endpoint: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Gửi GET request đến backend C# gAMSPro API."""
    return await request_backend_api("GET", endpoint, params=params)
