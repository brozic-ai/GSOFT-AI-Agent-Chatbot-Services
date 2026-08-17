import logging
from typing import Any, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Token cache trong bộ nhớ tạm để tránh gọi login liên tục
_TOKEN_CACHE: dict[str, str] = {"token": ""}


async def get_backend_auth_token(force_refresh: bool = False) -> str:
    """Lấy Bearer JWT Token từ C# Backend API TokenAuth (chuẩn ABP Framework)."""
    if _TOKEN_CACHE["token"] and not force_refresh:
        return _TOKEN_CACHE["token"]

    login_url = f"{settings.NET_BACKEND_URL}/api/TokenAuth/Authenticate"
    auth_payload = {
        "userNameOrEmailAddress": "baotq",
        "password": "Gsoft@#hai0hai6",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(login_url, json=auth_payload)
            if res.status_code == 200:
                data = res.json()
                token = data.get("result", {}).get("accessToken", "")
                if token:
                    _TOKEN_CACHE["token"] = token
                    return token
                logger.error("TokenAuth response did not contain accessToken")
                raise RuntimeError("Phản hồi đăng nhập không chứa token hợp lệ.")
            else:
                logger.error(f"Failed to authenticate with C# backend ({res.status_code}): {res.text}")
                raise RuntimeError(f"Xác thực với hệ thống gAMSPro thất bại ({res.status_code}).")
    except Exception as e:
        logger.exception("Error during get_backend_auth_token")
        raise RuntimeError(f"Không thể kết nối đến máy chủ gAMSPro: {str(e)}")


async def request_backend_api(
    method: str,
    endpoint: str,
    payload: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Gửi HTTP Request (POST / GET) đến backend C# gAMSPro API với cơ chế tự động refresh token khi 401."""
    url = f"{settings.NET_BACKEND_URL}{endpoint}"
    token = await get_backend_auth_token()

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

        # Nếu token hết hạn (401), làm mới token và thử lại 1 lần
        if res.status_code == 401:
            logger.warning("Bearer token expired (401). Refreshing token and retrying...")
            token = await get_backend_auth_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            req_kwargs["headers"] = headers
            res = await client.request(method.upper(), url, **req_kwargs)

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
