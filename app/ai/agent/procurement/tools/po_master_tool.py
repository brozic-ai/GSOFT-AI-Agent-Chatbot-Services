import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api
from app.ai.agent.procurement.tools.status_formatter import format_status_badge
from app.core.user_context import get_resolved_user_name

logger = logging.getLogger(__name__)


class GetPoMasterStatusInput(BaseModel):
    po_code: Optional[str] = Field(
        default=None,
        description="Mã Đơn đặt hàng PO (ví dụ dạng tương đối: 'PO...' hoặc để trống nếu muốn xem danh sách các đơn hàng PO gần đây).",
    )


@tool("get_po_master_status", args_schema=GetPoMasterStatusInput)
async def get_po_master_status(
    po_code: Optional[str] = None,
    **kwargs,
) -> str:
    """Tra cứu Đơn đặt hàng PO (Purchase Order / Phiếu gọi hàng) và tiến độ giao hàng trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Tra cứu tình trạng đơn đặt hàng PO theo mã PO (ví dụ dạng: 'PO...').
    - Xem danh sách các PO đang triển khai, giá trị đơn hàng, Nhà cung cấp và hạn giao hàng từ API.
    - TUYỆT ĐỐI KHÔNG dùng tool này để xem chi tiết Tờ trình mua sắm (hãy dùng get_request_doc_detail).
    """
    try:
        raw_code = po_code or kwargs.get("ma_po") or kwargs.get("po_no") or kwargs.get("doc_no") or ""
        clean_code = str(raw_code).strip().strip("<>").strip()
        uname = get_resolved_user_name()
        if not uname:
            return "⚠️ Bạn chưa đăng nhập tài khoản gAMSPro. Vui lòng đăng nhập để tra cứu Đơn đặt hàng PO."

        is_request_doc = clean_code.upper().startswith("PUR/") or clean_code.upper().startswith("TRRD")

        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "pO_CODE": "" if is_request_doc else clean_code,
            "level": "ALL",
            "useR_LOGIN": uname,
        }

        data = await post_backend_api("/api/TradePoMaster/TR_PO_MASTER_Search", payload=payload)
        result = data.get("result", {})
        items = result.get("items", [])
        total = result.get("totalCount", len(items))

        if not items:
            if is_request_doc:
                return (
                    f"Hiện tại chưa có Đơn đặt hàng (PO) nào được phát hành trực tiếp từ Tờ trình `{clean_code}` trên gAMSPro. "
                    "Đây là thông tin nghiệp vụ bình thường (hồ sơ có thể đang ở bước xét duyệt hoặc chưa phát hành PO)."
                )
            search_target = f"khớp với mã '{clean_code}'" if clean_code else f"của cán bộ '{uname}'"
            return (
                f"Hiện tại hệ thống gAMSPro chưa ghi nhận Đơn đặt hàng (PO) nào {search_target}. "
                "Đây là dữ liệu thực tế từ hệ thống (không phải lỗi kỹ thuật)."
            )

        prefix_note = ""
        if is_request_doc:
            prefix_note = (
                f"Thông tin: Hiện tại chưa có Đơn đặt hàng PO nào được tạo trực tiếp từ Tờ trình `{clean_code}`.\n"
                f"Dưới đây là danh sách các Đơn đặt hàng PO đang triển khai trên hệ thống:\n\n"
            )

        table_rows = [
            "| STT | Mã PO | Tên gói / Nội dung | Nhà cung cấp | Tổng giá trị PO | Trạng thái | Ngày lập |",
            "| :---: | :--- | :--- | :--- | ---: | :--- | :---: |",
        ]

        for idx, item in enumerate(items[:5], 1):
            amt = float(item.get("totaL_AMT") or item.get("poAmt") or 0)
            amt_str = f"{amt:,.0f} VNĐ"
            p_code = item.get("pO_CODE") or item.get("poCode") or "N/A"
            po_name = (item.get("pO_NAME") or item.get("poName") or "Không có").replace("|", "-").strip()
            supplier = (item.get("suP_NAME") or item.get("supplierName") or "Không có").replace("|", "-").strip()
            status = item.get("autH_STATUS_NAME") or item.get("statusName") or "Không xác định"
            po_dt = (item.get("pO_DT") or item.get("creatE_DT") or "N/A")[:10]

            status_badge = format_status_badge(status)

            table_rows.append(
                f"| {idx} | `{p_code}` | {po_name} | {supplier} | {amt_str} | {status_badge} | {po_dt} |"
            )

        summary = (
            prefix_note
            + f"📊 **Tìm thấy tổng cộng {total} Đơn hàng PO trên gAMSPro** (hiển thị {len(items[:5])} PO gần nhất):\n\n"
            + "\n".join(table_rows)
            + "\n\n💡 **Gợi ý:** Bạn có thể tra cứu chi tiết tiến độ hoặc kiểm tra Tờ trình mua sắm liên quan."
        )
        return summary

    except Exception as e:
        from app.ai.agent.procurement.tools.error_handler import format_procurement_tool_error
        return format_procurement_tool_error("tra cứu đơn hàng PO", e)
