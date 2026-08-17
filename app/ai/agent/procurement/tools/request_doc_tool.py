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


@tool("search_request_docs", args_schema=SearchRequestDocsInput)
async def search_request_docs(
    so_to_trinh: Optional[str] = None,
    user_name: Optional[str] = None,
    type_job: Optional[str] = "DVKD",
) -> str:
    """Tra cứu danh sách hoặc thông tin cơ bản của Tờ trình Mua sắm/Nghiệp vụ trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Xem danh sách các tờ trình mua sắm đã lập gần đây.
    - Tìm kiếm tờ trình theo mã số (ví dụ: "PUR/2025/000052").
    - Tra cứu trạng thái phê duyệt, người lập, số tiền đề xuất từ dữ liệu API.
    """
    try:
        uname = (user_name or "").strip() or "baotq"
        payload = {
            "maxResultCount": 5,
            "skipCount": 0,
            "reQ_CODE": so_to_trinh.strip() if so_to_trinh else "",
            "type": type_job or "DVKD",
            "tlnamE_USER": uname,
        }

        data = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=payload)
        result = data.get("result", {})
        items = result.get("items", [])[:5]
        total = result.get("totalCount", 0)

        if not items:
            search_target = f"khớp với mã '{so_to_trinh}'" if so_to_trinh else f"của cán bộ '{uname}'"
            return f"Không tìm thấy tờ trình nào {search_target} trên hệ thống gAMSPro."

        formatted_results = []
        for idx, item in enumerate(items, 1):
            amt = float(item.get("totaL_AMT") or 0)
            amt_str = f"{amt:,.0f} VNĐ"
            auth_status = item.get("autH_STATUS_NAME") or "Không xác định"
            process_status = item.get("procesS_STATUS_NEXT") or item.get("procesS_STATUS") or ""
            status_display = f"{auth_status} ({process_status})" if process_status else auth_status
            maker = item.get("makeR_NAME") or item.get("useR_REQUEST_NAME") or "N/A"
            dep = item.get("deP_CREATE_NAME") or "N/A"
            branch = item.get("brancH_NAME_DVMS") or item.get("brancH_DO_NAME") or item.get("brancH_CREATE_NAME") or "N/A"
            req_code = item.get("reQ_CODE") or "N/A"
            req_id = item.get("reQ_ID") or "N/A"
            req_dt = item.get("reQ_DT") or item.get("creatE_DT") or "N/A"
            reason = item.get("reQ_REASON") or "Không có"
            plan_code = item.get("pL_REQ_CODE") or "Chưa liên kết"

            doc_info = (
                f"{idx}. Số Tờ trình: {req_code}\n"
                f"   - Mã hệ thống (REQ_ID): {req_id}\n"
                f"   - Trạng thái duyệt: {status_display}\n"
                f"   - Người tạo: {maker} (Phòng: {dep})\n"
                f"   - Đơn vị: {branch}\n"
                f"   - Tổng tiền đề xuất: {amt_str}\n"
                f"   - Ngày lập: {req_dt}\n"
                f"   - Trích yếu / Lý do: {reason}\n"
                f"   - Mã Kế hoạch liên kết: {plan_code}"
            )
            formatted_results.append(doc_info)

        summary = (
            f"Tìm thấy tổng cộng {total} tờ trình trên gAMSPro. Dưới đây là thông tin chi tiết:\n\n"
            + "\n\n".join(formatted_results)
        )
        return summary

    except Exception as e:
        logger.exception("Error executing search_request_docs tool")
        return f"Lỗi kết nối gAMSPro khi tra cứu tờ trình: {str(e)}"
