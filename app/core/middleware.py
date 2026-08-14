"""
Middleware tập trung cho ứng dụng FastAPI.

Bao gồm:
- RequestLoggingMiddleware: Ghi log mọi request/response kèm thời gian xử lý.
- APIKeyAuthMiddleware: Xác thực API Key qua header cho các request nội bộ.
- GlobalExceptionMiddleware: Bắt mọi exception chưa xử lý, trả về response chuẩn.
"""

import logging
import time
import traceback

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


# 1. Request Logging Middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Ghi log cho mỗi request đi vào:
    - Method, URL, Client IP
    - Thời gian xử lý (ms)
    - Status code trả về
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()

        # Lấy client IP (hỗ trợ proxy qua X-Forwarded-For)
        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        )

        logger.info(
            "--> %s %s [client=%s]",
            request.method,
            request.url.path,
            client_ip,
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "<-- %s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        # Thêm header timing vào response (hữu ích cho debugging)
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"

        return response


# 2. API Key Authentication Middleware

# Danh sách các path được phép truy cập không cần API Key
_PUBLIC_PATHS: list[str] = [
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    f"{settings.API_V1_STR}/health",
]


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Kiểm tra header `X-Internal-Api-Key` trên mọi request.
    - Bỏ qua với OPTIONS (CORS preflight) và các public paths.
    - Nếu REQUIRED_API_KEY rỗng → tắt tính năng auth (dev mode).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Bỏ qua preflight CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        # Bỏ qua các endpoint công khai
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Nếu không cấu hình API key → cho qua (dev mode)
        required_key = getattr(settings, "REQUIRED_API_KEY", "")
        if not required_key:
            return await call_next(request)

        # Kiểm tra API key từ header
        provided_key = request.headers.get("X-Internal-Api-Key", "")
        if provided_key != required_key:
            logger.warning(
                "[DENIED] Unauthorized request: %s %s [client=%s]",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Unauthorized: Invalid or missing X-Internal-Api-Key"
                },
            )

        return await call_next(request)


# 3. Global Exception Handler Middleware
class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """
    Bắt mọi exception chưa được xử lý bởi các handler cụ thể,
    trả về JSON response chuẩn thay vì để server crash hoặc trả HTML 500.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(
                "[ERROR] Unhandled exception on %s %s: %s\n%s",
                request.method,
                request.url.path,
                str(exc),
                traceback.format_exc(),
            )

            # Trong production, ẩn chi tiết lỗi
            detail = (
                str(exc)
                if settings.ENVIRONMENT != "production"
                else "Internal Server Error"
            )

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": detail,
                    "type": type(exc).__name__,
                },
            )


# Hàm đăng ký tất cả middleware vào app
def register_middlewares(app: FastAPI) -> None:
    """
    Đăng ký toàn bộ custom middleware vào FastAPI app.

    Thứ tự đăng ký (ngược với thứ tự thực thi):
    - Middleware đăng ký SAU sẽ chạy TRƯỚC (outermost).
    - Vì vậy ta đăng ký theo thứ tự: Exception → Auth → Logging
      → Request sẽ đi qua: Logging → Auth → Exception → Handler
    """
    # Đăng ký sau cùng → chạy ngoài cùng (đầu tiên nhận request)
    app.add_middleware(GlobalExceptionMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
