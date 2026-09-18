import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api
from app.ai.agent.procurement.tools.status_formatter import format_status_badge
from app.core.user_context import get_resolved_user_name

logger = logging.getLogger(__name__)


class GetRequestDocDetailInput(BaseModel):
    doc_id: str = Field(
        description="Mã số Tờ trình mua sắm cần xem chi tiết (ví dụ: 'PUR/...' hoặc 'TRRD...'). Bắt buộc.",
    )


@tool("get_request_doc_detail", args_schema=GetRequestDocDetailInput)
async def get_request_doc_detail(
    doc_id: Optional[str] = None,
    **kwargs,
) -> str:
    """Tra cứu thông tin chi tiết đầy đủ của một Tờ trình mua sắm cụ thể trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Xem chi tiết 1 tờ trình (ví dụ dạng: 'PUR/...' hoặc 'TRRD...').
    - Xem người lập, phòng ban chịu phí, tổng số tiền đề xuất, kế hoạch liên kết, nội dung lý do từ API.
    - Kiểm tra trạng thái phê duyệt chi tiết để đối soát ngân sách.
    """
    try:
        raw_id = doc_id or kwargs.get("doc_identifier") or kwargs.get("req_id") or kwargs.get("so_to_trinh") or kwargs.get("doc_no") or ""
        clean_id = str(raw_id).strip().strip("<>").strip()
        if not clean_id:
            return (
                "⚠️ THÔNG BÁO CHO NGƯỜI DÙNG: Không xác định được mã Tờ trình cần xem chi tiết. "
                "Vui lòng hướng dẫn người dùng cung cấp chính xác mã số Tờ trình (ví dụ dạng: 'PUR/...') hoặc mã REQ_ID (ví dụ dạng: 'TRRD...'). "
                "Tuyệt đối không tự ý gọi lại tool này."
            )
        resolved_req_id = clean_id
        doc_code = clean_id
        search_item = None
        uname = get_resolved_user_name()
        if not uname:
            return "⚠️ Bạn chưa đăng nhập tài khoản gAMSPro. Vui lòng đăng nhập để xem chi tiết tờ trình."

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
            items = search_res.get("result", {}).get("items", []) if isinstance(search_res, dict) else []
            # Nếu tìm theo user không thấy, thử tìm lại không truyền tlnamE_USER (xem tờ trình phòng ban khác nếu có quyền)
            if not items:
                search_payload["tlnamE_USER"] = ""
                search_res = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=search_payload)
                items = search_res.get("result", {}).get("items", []) if isinstance(search_res, dict) else []

            if items:
                search_item = items[0]
                resolved_req_id = search_item.get("reQ_ID", clean_id)
                doc_code = search_item.get("reQ_CODE", clean_id)
            else:
                return f"Không tìm thấy thông tin chi tiết cho Tờ trình '{clean_id}' trên hệ thống gAMSPro."

        # Gọi API ById để lấy chi tiết đầy đủ
        try:
            params = {"id": resolved_req_id, "userLogin": uname}
            raw_res = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_ById", params=params)
            item = raw_res.get("result", raw_res) if isinstance(raw_res, dict) and "result" in raw_res else raw_res
        except Exception:
            item = None

        # Fallback nếu ById trả về rỗng nhưng search_item có dữ liệu
        if (not item or not isinstance(item, dict) or not item.get("reQ_ID")) and search_item:
            item = search_item

        if not item or not isinstance(item, dict) or not item.get("reQ_ID"):
            return f"Không tìm thấy thông tin chi tiết cho Tờ trình '{clean_id}' trên hệ thống gAMSPro."

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

        # Gợi ý hành động thông minh theo trạng thái
        suggestion_lines = []
        is_draft = "lưu nháp" in status_display.lower() or "draft" in status_display.lower()
        if is_draft:
            suggestion_lines.append(f"- Tờ trình đang ở trạng thái **Lưu Nháp**. Bạn có thể gửi phê duyệt ngay bằng cách nói: *\"Gửi duyệt tờ trình {item.get('reQ_CODE', doc_code)}\"*.")
        elif "chờ" in status_display.lower() or "trình duyệt" in status_display.lower():
            suggestion_lines.append("- Tờ trình đang chờ cấp thẩm quyền phê duyệt. Bạn có thể theo dõi tiến độ hoặc liên hệ người duyệt tiếp theo.")
        if plan_code and "chưa" not in plan_code.lower():
            suggestion_lines.append(f"- Bạn có thể kiểm tra hạn mức ngân sách bằng cách nói: *\"Kiểm tra ngân sách kế hoạch {plan_code}\"*.")

        suggestions_text = ""
        if suggestion_lines:
            suggestions_text = "\n\n💡 **Hành động gợi ý:**\n" + "\n".join(suggestion_lines)

        status_badge = format_status_badge(status_display)

        detail_info = (
            f"### 📋 Chi tiết Tờ trình: `{item.get('reQ_CODE', doc_code)}`\n\n"
            f"- **Tên tờ trình / Trích yếu:** **{reason}**\n"
            f"- **Tổng tiền đề xuất:** **{amt_str}**\n"
            f"- **Trạng thái phê duyệt:** {status_badge}\n"
            f"- **Mã định danh hệ thống (REQ_ID):** `{req_sys_id}`\n"
            f"- **Người lập:** {maker} (Phòng: {dep} — {branch})\n"
            f"- **Đơn vị chịu chi phí:** {branch} — {dep}\n"
            f"- **Ngày tạo tờ trình:** {create_dt}\n"
            f"- **Kế hoạch liên kết:** 📌 `{plan_code}`\n\n"
            f"👉 [Nhấn vào đây để xem chi tiết và thao tác trên gAMSPro](/app/admin/request-doc-view;id={req_sys_id})"
            f"{suggestions_text}"
        )
        return detail_info

    except Exception as e:
        from app.ai.agent.procurement.tools.error_handler import format_procurement_tool_error
        return format_procurement_tool_error("tra cứu chi tiết tờ trình", e)
