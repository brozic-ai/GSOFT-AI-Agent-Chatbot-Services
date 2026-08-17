"""
Module Enterprise Rate Limiting & Concurrency Engine cho hệ thống Local AI Agent.

Bao gồm:
- Phân tầng Role Quota (Admin / Manager / Staff).
- Sliding Window Rate Limiter (RPM) theo User-ID.
- Concurrency Limiter (Giới hạn luồng Streaming đồng thời trên mỗi User).
- Thread-safe / Async-safe với asyncio.Lock.
"""

import asyncio
from collections import deque
from enum import Enum
import logging
import math
import time
from typing import Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class RoleTier(str, Enum):
    """Phân tầng người dùng trong hệ thống Ngân hàng."""
    ADMIN = "Admin"
    MANAGER = "Manager"
    STAFF = "Staff"


# Danh sách từ khóa và GUID nhận diện quyền Admin (đồng bộ với DocumentRepository)
_ADMIN_KEYWORDS = {
    "admin",
    "administrator",
    "administrators",
    "fulltemp",
    "sysadmin",
    "superadmin",
    "4ff86c2b184f46bebb5cc338c74b5669",
}

# Danh sách từ khóa nhận diện cấp Quản lý / Phê duyệt
_MANAGER_KEYWORDS = {
    "manager",
    "approver",
    "lead",
    "leader",
    "truongphong",
    "phophong",
    "giamdoc",
    "director",
    "supervisor",
    "quanly",
}


def resolve_role_tier(roles: Optional[str]) -> RoleTier:
    """
    Xác định RoleTier từ chuỗi danh sách vai trò người dùng (phân cách bằng dấu phẩy).

    Thứ tự ưu tiên:
    1. Admin / SuperAdmin / System (Tier cao nhất)
    2. Manager / Approver / Leader (Tier trung cấp)
    3. Staff / Employee (Tier mặc định cho nhân viên ngân hàng)
    """
    if not roles:
        return RoleTier.STAFF

    roles_lower = [r.strip().lower() for r in roles.split(",") if r.strip()]
    if not roles_lower:
        return RoleTier.STAFF

    # 1. Kiểm tra Admin
    if any(
        r in _ADMIN_KEYWORDS
        or any(kw in r for kw in ("admin", "fulltemp", "sysadmin", "superadmin"))
        for r in roles_lower
    ):
        return RoleTier.ADMIN

    # 2. Kiểm tra Manager
    if any(
        r in _MANAGER_KEYWORDS
        or any(kw in r for kw in _MANAGER_KEYWORDS)
        for r in roles_lower
    ):
        return RoleTier.MANAGER

    # 3. Mặc định là Staff
    return RoleTier.STAFF


class RateLimiter:
    """
    Bộ điều tiết lưu lượng và giới hạn kết nối đồng thời theo User-ID.
    Sử dụng Sliding Window Counter và In-flight Concurrency Tracker (In-Memory).
    """

    def __init__(self) -> None:
        self._inflight: dict[str, int] = {}
        self._rpm_history: dict[str, deque[float]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    def get_tier_quotas(self, tier: RoleTier) -> Tuple[int, int]:
        """
        Trả về (rpm_limit, concurrency_limit) theo RoleTier.
        Giá trị 0 biểu thị không giới hạn (Bypass).
        """
        if tier == RoleTier.ADMIN:
            return (settings.RATE_LIMIT_ADMIN_RPM, settings.CHAT_CONCURRENCY_ADMIN)
        elif tier == RoleTier.MANAGER:
            return (settings.RATE_LIMIT_MANAGER_RPM, settings.CHAT_CONCURRENCY_MANAGER)
        else:
            return (settings.RATE_LIMIT_STAFF_RPM, settings.CHAT_CONCURRENCY_STAFF)

    async def check_and_acquire(
        self,
        user_id: str,
        roles: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> RoleTier:
        """
        Kiểm tra và chiếm 1 slot xử lý (Concurrency + RPM).
        Nếu vượt ngưỡng, ném HTTPException(429) kèm headers RFC Retry-After.

        Trả về RoleTier đã được phân giải.
        """
        if not settings.RATE_LIMIT_ENABLED:
            return resolve_role_tier(roles)

        clean_user_id = str(user_id).strip()
        if not clean_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Missing or empty user identifier.",
            )

        tier = resolve_role_tier(roles)
        rpm_limit, concurrency_limit = self.get_tier_quotas(tier)

        async with self._lock:
            # 1. Kiểm tra Concurrency (Số luồng streaming đồng thời)
            current_inflight = self._inflight.get(clean_user_id, 0)
            if concurrency_limit > 0 and current_inflight >= concurrency_limit:
                logger.warning(
                    "[AUDIT-BLOCKED] Concurrency limit exceeded for user='%s' | tier=%s | inflight=%d | max=%d | traceId='%s'",
                    clean_user_id,
                    tier.value,
                    current_inflight,
                    concurrency_limit,
                    request_id or "",
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Hệ thống đang trả lời câu hỏi trước của bạn, vui lòng đợi hoàn tất.",
                    headers={
                        "Retry-After": "2",
                        "X-RateLimit-Blocked-Reason": "concurrency_exceeded",
                    },
                )

            # 2. Kiểm tra RPM Sliding Window (Tần suất gọi trong 60 giây)
            now = time.monotonic()
            if clean_user_id not in self._rpm_history:
                self._rpm_history[clean_user_id] = deque()

            history = self._rpm_history[clean_user_id]
            # Loại bỏ các timestamp cũ hơn 60 giây
            while history and history[0] <= now - 60.0:
                history.popleft()

            if rpm_limit > 0 and len(history) >= rpm_limit:
                oldest_ts = history[0]
                retry_after = max(1, int(math.ceil(60.0 - (now - oldest_ts))))
                logger.warning(
                    "[AUDIT-BLOCKED] RPM limit exceeded for user='%s' | tier=%s | count=%d | limit=%d | retry_after=%ds | traceId='%s'",
                    clean_user_id,
                    tier.value,
                    len(history),
                    rpm_limit,
                    retry_after,
                    request_id or "",
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Bạn đã vượt quá giới hạn {rpm_limit} yêu cầu/phút. Vui lòng thử lại sau {retry_after} giây.",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(rpm_limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Blocked-Reason": "rpm_exceeded",
                    },
                )

            # 3. Tất cả điều kiện hợp lệ -> Cập nhật trạng thái
            history.append(now)
            self._inflight[clean_user_id] = current_inflight + 1

            logger.info(
                "[AUDIT-ALLOWED] Rate limit slot acquired | user='%s' | tier=%s | inflight=%d | rpm_used=%d/%d | traceId='%s'",
                clean_user_id,
                tier.value,
                self._inflight[clean_user_id],
                len(history),
                rpm_limit,
                request_id or "",
            )
            return tier

    async def release(
        self,
        user_id: str,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Giải phóng slot Concurrency sau khi hoàn tất stream hoặc khi request bị hủy / lỗi.
        """
        if not settings.RATE_LIMIT_ENABLED:
            return

        clean_user_id = str(user_id).strip()
        if not clean_user_id:
            return

        async with self._lock:
            if clean_user_id in self._inflight:
                self._inflight[clean_user_id] = max(0, self._inflight[clean_user_id] - 1)
                if self._inflight[clean_user_id] == 0:
                    del self._inflight[clean_user_id]

                logger.debug(
                    "[AUDIT-RELEASE] Concurrency slot released | user='%s' | remaining_inflight=%d | traceId='%s'",
                    clean_user_id,
                    self._inflight.get(clean_user_id, 0),
                    request_id or "",
                )

    def get_status(self, user_id: str) -> dict:
        """Lấy trạng thái quota hiện tại của user phục vụ audit/monitoring."""
        clean_user_id = str(user_id).strip()
        now = time.monotonic()
        history = self._rpm_history.get(clean_user_id, deque())
        valid_requests = sum(1 for ts in history if ts > now - 60.0)
        return {
            "user_id": clean_user_id,
            "inflight": self._inflight.get(clean_user_id, 0),
            "rpm_used_last_60s": valid_requests,
        }

    async def reset(self) -> None:
        """Reset toàn bộ trạng thái limiter (Dùng cho Unit Tests)."""
        async with self._lock:
            self._inflight.clear()
            self._rpm_history.clear()


# Singleton Instance
rate_limiter = RateLimiter()
