import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api
from app.ai.agent.procurement.tools.status_formatter import format_status_badge
from app.core.user_context import get_resolved_user_name

logger = logging.getLogger(__name__)


class SearchRequestDocsInput(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
        description="Số thứ tự trang cần tra cứu (bắt đầu từ trang 1).",
    )
    page_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Số lượng tờ trình hiển thị (mặc định 10 tờ trình đầu tiên).",
    )
    doc_code: Optional[str] = Field(
        default=None,
        description="Mã số tờ trình cần tra cứu (ví dụ dạng: 'PUR/...').",
    )
    status: Optional[str] = Field(
        default=None,
        description="Bộ lọc trạng thái phê duyệt (ví dụ: 'Lưu Nháp', 'Chờ duyệt', 'Đã duyệt').",
    )


@tool("search_request_docs", args_schema=SearchRequestDocsInput)
async def search_request_docs(
    page: int = 1,
    page_size: int = 10,
    doc_code: Optional[str] = None,
    status: Optional[str] = None,
    type_job: Optional[str] = "DVKD",
    **kwargs,
) -> str:
    """Tra cứu danh sách hoặc thông tin cơ bản của Tờ trình Mua sắm/Nghiệp vụ trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Xem danh sách các tờ trình mua sắm đã lập gần đây (mặc định hiển thị 10 tờ trình đầu tiên).
    - Tìm kiếm tờ trình theo mã số (ví dụ: 'PUR/...').
    - Tra cứu trạng thái phê duyệt, người lập, số tiền đề xuất từ dữ liệu API.
    """
    try:
        uname = get_resolved_user_name()
        if not uname:
            return "⚠️ Bạn chưa đăng nhập tài khoản gAMSPro. Vui lòng đăng nhập để xem danh sách tờ trình."

        skip_count = max(0, (page - 1) * page_size)
        raw_code = doc_code or kwargs.get("so_to_trinh") or kwargs.get("doc_identifier") or ""
        code_val = str(raw_code).strip().strip("<>").strip()
        payload = {
            "maxResultCount": page_size,
            "skipCount": skip_count,
            "reQ_CODE": code_val,
            "type": type_job or "DVKD",
            "tlnamE_USER": uname,
        }

        data = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=payload)
        result = data.get("result", {})
        raw_items = result.get("items", [])
        total = result.get("totalCount", len(raw_items))

        # Lọc trạng thái trong bộ nhớ nếu người dùng yêu cầu lọc cụ thể
        items = raw_items
        effective_status = (status or kwargs.get("status_filter") or kwargs.get("status_name") or "").strip()
        # Bỏ qua các từ khóa phi trạng thái (như 'gần đây', 'recent', 'mới nhất', 'tất cả')
        IGNORE_STATUS_KEYWORDS = ("gần đây", "mới nhất", "recent", "all", "tất cả", "gần", "danh sách")
        if effective_status and effective_status.lower() in IGNORE_STATUS_KEYWORDS:
            effective_status = ""

        if effective_status:
            kw = effective_status.lower()
            items = [
                it for it in items
                if kw in (it.get("autH_STATUS_NAME") or "").lower()
                or kw in (it.get("procesS_STATUS_NEXT") or "").lower()
                or kw in (it.get("procesS_STATUS") or "").lower()
            ]

        if not items:
            search_target = f"khớp với mã '{code_val}'" if code_val else ""
            if effective_status:
                search_target += f" với trạng thái '{effective_status}'"
            target_desc = f" {search_target}" if search_target else ""
            return f"Không tìm thấy tờ trình nào{target_desc} trên hệ thống gAMSPro."

        start_idx = skip_count + 1

        # Định dạng dạng Bảng Markdown tiêu chuẩn
        table_rows = [
            "| STT | Số Tờ trình | Trích yếu / Lý do | Tổng tiền đề xuất | Trạng thái | Ngày lập |",
            "| :---: | :--- | :--- | ---: | :--- | :---: |",
        ]

        for i, item in enumerate(items, start_idx):
            amt = float(item.get("totaL_AMT") or 0)
            amt_str = f"{amt:,.0f} VNĐ"
            auth_status = item.get("autH_STATUS_NAME") or "Không xác định"
            process_status = item.get("procesS_STATUS_NEXT") or item.get("procesS_STATUS") or ""
            status_display = f"{auth_status} ({process_status})" if process_status else auth_status

            # Rút gọn và chuẩn hóa trạng thái cho bảng để hiển thị badge màu trên Chatbot UI
            status_badge = format_status_badge(status_display)

            req_code = item.get("reQ_CODE") or "N/A"
            req_dt = (item.get("reQ_DT") or item.get("creatE_DT") or "N/A")[:10]  # Lấy định dạng YYYY-MM-DD
            reason = (item.get("reQ_REASON") or "Không có").replace("|", "-").strip()
            # Cắt ngắn lý do nếu dài hơn 45 ký tự để bảng gọn gàng
            if len(reason) > 45:
                reason = reason[:42] + "..."

            table_rows.append(
                f"| {i} | `{req_code}` | {reason} | {amt_str} | {status_badge} | {req_dt} |"
            )

        summary_header = (
            f"📊 **Tìm thấy tổng cộng {total} tờ trình trên gAMSPro** "
            f"(Hiển thị {len(items)} tờ trình gần đây nhất):\n\n"
        )
        table_content = "\n".join(table_rows)

        # Hướng dẫn gợi ý tương tác tiếp theo (không gợi ý phân trang)
        footer_tips = [
            "\n\n💡 **Gợi ý thao tác tiếp theo:**",
            "- Để xem chi tiết hồ sơ: Bạn hãy nói *\"Cho tôi xem chi tiết tờ trình đầu tiên\"* hoặc *\"Xem chi tiết PUR/...\"*."
        ]

        return summary_header + table_content + "\n".join(footer_tips)

    except Exception as e:
        logger.exception("Error executing search_request_docs tool")
        return f"Lỗi kết nối gAMSPro khi tra cứu tờ trình: {str(e)}"
