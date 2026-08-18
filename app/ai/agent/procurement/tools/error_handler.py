"""
Procurement Tool Error Handling & Fallback Interceptor.
Bắt và chuyển đổi các ngoại lệ kỹ thuật từ API gAMSPro thành thông báo nghiệp vụ thân thiện.
"""

import logging

logger = logging.getLogger(__name__)


def format_procurement_tool_error(action_name: str, ex: Exception) -> str:
    """
    Bắt và chuyển đổi các lỗi gọi API gAMSPro (500, Timeout, Network Error) thành thông điệp thân thiện.
    """
    err_str = str(ex)
    logger.error("[PROCUREMENT TOOL ERROR] Lỗi khi thực thi '%s': %s", action_name, ex, exc_info=True)

    # 1. Phát hiện lỗi Timeout
    if "timeout" in err_str.lower() or "timed out" in err_str.lower():
        return (
            f"⚠️ Hệ thống gAMSPro hiện đang phản hồi chậm khi {action_name}. "
            f"Bạn vui lòng thử lại sau ít phút hoặc thực hiện trực tiếp trên giao diện web gAMSPro."
        )

    # 2. Phát hiện lỗi kết nối / 500 / 502 / 503 / 504 / Server error
    if any(code in err_str for code in ("500", "502", "503", "504", "Connection", "ConnectError", "Network")):
        return (
            f"⚠️ Dịch vụ gAMSPro hiện đang bảo trì hoặc gặp sự cố kỹ thuật khi {action_name}. "
            f"Bạn vui lòng thử lại sau ít phút hoặc thao tác trực tiếp trên cổng thông tin gAMSPro."
        )

    # 3. Lỗi nghiệp vụ từ gAMSPro trả về
    return f"⚠️ Không thể hoàn tất {action_name} trên gAMSPro do: {err_str}. Bạn vui lòng kiểm tra lại thông tin hoặc thực hiện trên web gAMSPro."
