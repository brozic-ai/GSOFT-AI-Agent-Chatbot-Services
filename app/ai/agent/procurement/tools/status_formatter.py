"""
Procurement Status Badge Formatter.
Chuẩn hóa icon và tiền tố trạng thái cho Tờ trình, Đơn hàng PO, Kế hoạch mua sắm
để Chatbot UI hiển thị thành badge màu (Pill Badge) trực quan.
"""

from typing import Optional


def format_status_badge(status_display: Optional[str]) -> str:
    """Format chuỗi trạng thái thành badge có icon chuẩn hóa cho Chatbot UI.

    Quy tắc màu trên giao diện Chatbot:
    - Warning (Vàng/Hổ phách): ⚠️ Lưu Nháp, Chưa liên kết
    - Success (Xanh lá cây):   ✅ Đã duyệt, Hoàn tất, Thành công
    - Danger  (Đỏ):            ❌ Từ chối, Đã hủy, Không duyệt
    - Info    (Xanh dương):    ⏳ Chờ duyệt, Đang xử lý, Trình duyệt
    """
    if not status_display:
        return "N/A"

    s = str(status_display).strip()
    s_lower = s.lower()

    if "lưu nháp" in s_lower or "draft" in s_lower:
        return "⚠️ Lưu Nháp"
    elif "đã duyệt" in s_lower or "hoàn tất" in s_lower or "approved" in s_lower:
        return "✅ Đã duyệt"
    elif "từ chối" in s_lower or "hủy" in s_lower or "reject" in s_lower or "không duyệt" in s_lower:
        return f"❌ {s}"
    elif "chờ" in s_lower or "đang" in s_lower or "trình duyệt" in s_lower or "pending" in s_lower:
        return f"⏳ {s}"
    return s
