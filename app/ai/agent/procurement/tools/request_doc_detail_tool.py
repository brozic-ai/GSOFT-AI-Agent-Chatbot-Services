import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api

logger = logging.getLogger(__name__)


class GetRequestDocDetailInput(BaseModel):
    doc_identifier: Optional[str] = Field(
        default=None,
        description="Mã số tờ trình (ví dụ: 'PUR/2025/000052') HOẶC Mã định danh hệ thống REQ_ID (ví dụ: 'TRRD00000269630').",
    )
    req_id: Optional[str] = Field(
        default=None,
        description="Mã REQ_ID hoặc Số tờ trình mua sắm.",
    )
    so_to_trinh: Optional[str] = Field(
        default=None,
        description="Số tờ trình mua sắm (ví dụ: 'PUR/2025/000052').",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ đang tra cứu (nếu không truyền sẽ dùng tài khoản đăng nhập hiện tại 'baotq').",
    )


@tool("get_request_doc_detail", args_schema=GetRequestDocDetailInput)
async def get_request_doc_detail(
    doc_identifier: Optional[str] = None,
    req_id: Optional[str] = None,
    so_to_trinh: Optional[str] = None,
    user_name: Optional[str] = None,
) -> str:
    """Tra cứu thông tin chi tiết đầy đủ của một Tờ trình mua sắm cụ thể trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Xem chi tiết chỉ tiêu của 1 tờ trình (như 'PUR/2025/000052' hoặc 'TRRD00000269630').
    - Xem người lập, phòng ban chịu phí, tổng số tiền đề xuất, kế hoạch liên kết, nội dung lý do từ API.
    - Kiểm tra trạng thái phê duyệt chi tiết để đối soát ngân sách.
    """
    try:
        target_id = (doc_identifier or req_id or so_to_trinh or "").strip()
        if not target_id:
            return "Vui lòng cung cấp Mã số Tờ trình (ví dụ: 'PUR/2025/000052') hoặc Mã hệ thống REQ_ID để tra cứu chi tiết."

        clean_id = target_id
        resolved_req_id = clean_id
        doc_code = clean_id
        search_item = None
        uname = (user_name or "").strip() or "baotq"

        # Nếu đầu vào không phải dạng TRRD..., tìm REQ_ID qua API search trước
        if not clean_id.upper().startswith("TRRD"):
            search_payload = {
                "maxResultCount": 5,
                "skipCount": 0,
                "reQ_CODE": clean_id,
                "type": "DVKD",
                "tlnamE_USER": uname,
            }
            search_res = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=search_payload)
            items = search_res.get("result", {}).get("items", [])
            if items:
                search_item = items[0]
                resolved_req_id = search_item.get("reQ_ID", clean_id)
                doc_code = search_item.get("reQ_CODE", clean_id)
            else:
                return f"Không tìm thấy thông tin chi tiết cho Tờ trình '{target_id}' trên hệ thống gAMSPro."

        # Gọi API ById để lấy chi tiết đầy đủ
        try:
            params = {"id": resolved_req_id, "userLogin": uname}
            item = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_ById", params=params)
        except Exception:
            item = None

        # Fallback nếu ById trả về rỗng nhưng search_item có dữ liệu
        if (not item or not item.get("reQ_ID")) and search_item:
            item = search_item

        if not item or not item.get("reQ_ID"):
            return f"Không tìm thấy thông tin chi tiết cho Tờ trình '{target_id}' trên hệ thống gAMSPro."

        amt = float(item.get("totaL_AMT") or 0)
        amt_str = f"{amt:,.0f} VNĐ"
        auth_status = item.get("autH_STATUS_NAME") or "Không xác định"
        process_status = item.get("procesS_STATUS_NEXT") or item.get("procesS_STATUS") or ""
        status_display = f"{auth_status} ({process_status})" if process_status else auth_status

        maker = item.get("makeR_NAME") or item.get("useR_REQUEST_NAME") or "N/A"
        dep = item.get("deP_CREATE_NAME") or item.get("brancH_DEP_REQUEST") or "N/A"
        branch = item.get("brancH_DO_NAME") or item.get("brancH_CREATE_NAME") or item.get("brancH_NAME_DVMS") or "N/A"
        reason = item.get("reQ_REASON") or "Không có"
        plan_code = item.get("pL_REQ_CODE") or "Chưa liên kết Kế hoạch"
        create_dt = item.get("creatE_DT") or item.get("reQ_DT") or "N/A"
        req_sys_id = item.get("reQ_ID") or "N/A"

        detail_info = (
            f"📋 CHI TIẾT TỜ TRÌNH: {item.get('reQ_CODE', doc_code)}\n"
            f"- Mã định danh hệ thống (REQ_ID): `{req_sys_id}`\n"
            f"- Người lập: {maker} (Phòng: {dep} — {branch})\n"
            f"- Đơn vị chịu chi phí: {branch} — {dep}\n"
            f"- Tổng tiền đề xuất: {amt_str}\n"
            f"- Ngày tạo tờ trình: {create_dt}\n"
            f"- Trạng thái: {status_display}\n"
            f"- Nội dung / Lý do: {reason}\n"
            f"- Kế hoạch liên kết: 📌 `{plan_code}`\n"
            f"- Đường dẫn xem và ký duyệt trên web: `/app/admin/request-doc-view;id={req_sys_id}`"
        )
        return detail_info

    except Exception as e:
        logger.exception("Error executing get_request_doc_detail tool")
        return f"Lỗi kết nối gAMSPro khi tra cứu chi tiết tờ trình: {str(e)}"
