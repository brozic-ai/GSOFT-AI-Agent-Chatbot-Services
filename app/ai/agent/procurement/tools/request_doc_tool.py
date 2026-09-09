import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api

logger = logging.getLogger(__name__)


class SearchRequestDocsInput(BaseModel):
    so_to_trinh: Optional[str] = Field(
        default=None,
        description="Mã số tờ trình cần tra cứu (ví dụ: 'PUR/2025/000052'). Nếu để trống hoặc rỗng sẽ lấy danh sách các tờ trình gần đây.",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ đang tra cứu trên gAMSPro (nếu không truyền sẽ dùng tài khoản đăng nhập hiện tại 'baotq').",
    )
    type_job: Optional[str] = Field(
        default="DVKD",
        description="Loại đơn vị lập tờ trình (DVKD: Đơn vị kinh doanh, DVMS: Đơn vị mua sắm). Mặc định 'DVKD'.",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Số thứ tự trang cần tra cứu (bắt đầu từ trang 1).",
    )
    page_size: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Số lượng tờ trình hiển thị trên một trang (mặc định 5, có thể tăng lên đến 35-50 nếu người dùng yêu cầu xem toàn bộ danh sách).",
    )
    status_filter: Optional[str] = Field(
        default=None,
        description="Bộ lọc trạng thái phê duyệt (ví dụ: 'Lưu Nháp', 'Chờ duyệt', 'Đã duyệt').",
    )


@tool("search_request_docs", args_schema=SearchRequestDocsInput)
async def search_request_docs(
    so_to_trinh: Optional[str] = None,
    user_name: Optional[str] = None,
    type_job: Optional[str] = "DVKD",
    page: int = 1,
    page_size: int = 5,
    status_filter: Optional[str] = None,
) -> str:
    """Tra cứu danh sách hoặc thông tin cơ bản của Tờ trình Mua sắm/Nghiệp vụ trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Xem danh sách các tờ trình mua sắm đã lập gần đây (hỗ trợ phân trang qua page và page_size).
    - Tìm kiếm tờ trình theo mã số (ví dụ: "PUR/2025/000052").
    - Tra cứu trạng thái phê duyệt, người lập, số tiền đề xuất từ dữ liệu API.
    """
    try:
        uname = (user_name or "").strip() or "baotq"
        skip_count = max(0, (page - 1) * page_size)
        payload = {
            "maxResultCount": page_size,
            "skipCount": skip_count,
            "reQ_CODE": so_to_trinh.strip() if so_to_trinh else "",
            "type": type_job or "DVKD",
            "tlnamE_USER": uname,
        }

        data = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=payload)
        result = data.get("result", {})
        raw_items = result.get("items", [])
        total = result.get("totalCount", len(raw_items))

        # Lọc trạng thái trong bộ nhớ nếu người dùng yêu cầu lọc cụ thể
        items = raw_items
        if status_filter:
            kw = status_filter.strip().lower()
            items = [
                it for it in items
                if kw in (it.get("autH_STATUS_NAME") or "").lower()
                or kw in (it.get("procesS_STATUS_NEXT") or "").lower()
                or kw in (it.get("procesS_STATUS") or "").lower()
            ]

        if not items:
            search_target = f"khớp với mã '{so_to_trinh}'" if so_to_trinh else f"của cán bộ '{uname}'"
            if status_filter:
                search_target += f" với trạng thái '{status_filter}'"
            return f"Không tìm thấy tờ trình nào {search_target} trên hệ thống gAMSPro."

        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = skip_count + 1
        end_idx = skip_count + len(items)

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

            # Rút gọn trạng thái cho bảng nếu quá dài
            if "Lưu Nháp" in status_display:
                status_badge = "⚠️ Lưu Nháp"
            elif "Đã duyệt" in status_display or "Hoàn tất" in status_display:
                status_badge = "✅ Đã duyệt"
            elif "Chờ" in status_display or "Từ chối" in status_display:
                status_badge = f"⏳ {status_display}"
            else:
                status_badge = status_display

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
            f"(Hiển thị trang {page}/{total_pages}, từ mục {start_idx} đến {end_idx}):\n\n"
        )
        table_content = "\n".join(table_rows)

        # Hướng dẫn gợi ý tương tác tiếp theo
        footer_tips = ["\n\n💡 **Gợi ý thao tác tiếp theo:**"]
        footer_tips.append("- Để xem chi tiết hồ sơ: Bạn hãy nói *\"Cho tôi xem chi tiết tờ trình đầu tiên\"* hoặc *\"Xem chi tiết PUR/...\"*.")
        if page < total_pages:
            footer_tips.append(f"- Để xem trang tiếp: Bạn hãy nói *\"Xem tiếp trang {page + 1}\"*.")
        if total > page_size and page_size < 35:
            footer_tips.append("- Để xem toàn bộ danh sách: Bạn hãy nói *\"Liệt kê tất cả 35 tờ trình\"*.")

        return summary_header + table_content + "\n".join(footer_tips)

    except Exception as e:
        logger.exception("Error executing search_request_docs tool")
        return f"Lỗi kết nối gAMSPro khi tra cứu tờ trình: {str(e)}"
