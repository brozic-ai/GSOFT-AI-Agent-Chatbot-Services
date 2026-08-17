import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api

logger = logging.getLogger(__name__)


class GetPoMasterStatusInput(BaseModel):
    ma_po: Optional[str] = Field(
        default=None,
        description="Mã Đơn đặt hàng PO (ví dụ: 'PO069/26/0006') HOẶC Mã Tờ trình mua sắm (ví dụ: 'PUR/2025/000052').",
    )
    po_code: Optional[str] = Field(
        default=None,
        description="Mã Đơn hàng PO (alias của ma_po).",
    )
    po_no: Optional[str] = Field(
        default=None,
        description="Mã Đơn hàng PO (alias của ma_po).",
    )
    doc_no: Optional[str] = Field(
        default=None,
        description="Mã Tờ trình mua sắm (alias của ma_po).",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ đang tra cứu (nếu không truyền sẽ dùng tài khoản đăng nhập hiện tại 'baotq').",
    )


@tool("get_po_master_status", args_schema=GetPoMasterStatusInput)
async def get_po_master_status(
    ma_po: Optional[str] = None,
    po_code: Optional[str] = None,
    po_no: Optional[str] = None,
    doc_no: Optional[str] = None,
    user_name: Optional[str] = None,
) -> str:
    """Tra cứu Đơn đặt hàng PO (Purchase Order / Phiếu gọi hàng) và tiến độ giao hàng trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Tra cứu tình trạng đơn đặt hàng PO theo mã PO (ví dụ: 'PO069/26/0006').
    - Kiểm tra xem một Tờ trình (ví dụ: 'PUR/2025/000052') đã được phát hành đơn hàng PO nào chưa.
    - Xem danh sách các PO đang triển khai, giá trị đơn hàng, Nhà cung cấp và hạn giao hàng từ API.
    """
    try:
        raw_code = po_code or po_no or doc_no or ma_po or ""
        clean_code = raw_code.strip()
        uname = (user_name or "").strip() or "baotq"
        is_request_doc = clean_code.upper().startswith("PUR/") or clean_code.upper().startswith("TRRD")

        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "pO_CODE": "" if is_request_doc else clean_code,
            "tlnamE_USER": uname,
        }

        data = await post_backend_api("/api/TradePoMaster/TR_PO_MASTER_Search", payload=payload)
        result = data.get("result", {})
        items = result.get("items", [])
        total = result.get("totalCount", 0)

        prefix_note = ""
        if is_request_doc:
            prefix_note = (
                f"Thông tin: Hiện tại chưa có Đơn đặt hàng PO nào được tạo trực tiếp từ Tờ trình `{clean_code}`.\n\n"
                f"Dưới đây là danh sách các Đơn đặt hàng PO đang triển khai trên hệ thống:\n\n"
            )

        if not items:
            if is_request_doc:
                return f"Hiện tại chưa có Đơn đặt hàng PO nào được tạo từ Tờ trình `{clean_code}`."
            search_target = f"khớp với mã '{clean_code}'" if clean_code else f"của cán bộ '{uname}'"
            return f"Không tìm thấy Đơn đặt hàng PO nào {search_target} trên hệ thống gAMSPro."

        formatted_results = []
        for idx, item in enumerate(items[:5], 1):
            amt = float(item.get("totaL_AMT") or item.get("poAmt") or 0)
            amt_str = f"{amt:,.0f} VNĐ"
            p_code = item.get("pO_CODE") or item.get("poCode") or "N/A"
            po_name = item.get("pO_NAME") or item.get("poName") or "Không có"
            supplier = item.get("suP_NAME") or item.get("supplierName") or "Không có"
            status = item.get("autH_STATUS_NAME") or item.get("statusName") or "Không xác định"
            po_dt = item.get("pO_DT") or item.get("creatE_DT") or "N/A"
            delivery_dt = item.get("deliverY_DT") or "Chưa xác định"

            info = (
                f"{idx}. Mã Đơn hàng PO: `{p_code}`\n"
                f"   - Tên gói / Nội dung: {po_name}\n"
                f"   - Trạng thái PO: {status}\n"
                f"   - Nhà cung cấp: {supplier}\n"
                f"   - Tổng giá trị PO: {amt_str}\n"
                f"   - Ngày lập PO: {po_dt}\n"
                f"   - Hạn giao hàng: {delivery_dt}"
            )
            formatted_results.append(info)

        summary = (
            prefix_note
            + f"Tìm thấy tổng cộng {total} Đơn hàng PO trên gAMSPro. Chi tiết:\n\n"
            + "\n\n".join(formatted_results)
        )
        return summary

    except Exception as e:
        logger.exception("Error executing get_po_master_status tool")
        return f"Lỗi kết nối gAMSPro khi tra cứu đơn hàng PO: {str(e)}"
