import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api

logger = logging.getLogger(__name__)


class SubmitRequestDocInput(BaseModel):
    doc_identifier: str = Field(
        description="Mã Tờ trình Mua sắm cần gửi phê duyệt (ví dụ: 'PUR/2026/000086' hoặc mã hệ thống 'TRRD00000269717'). Bắt buộc.",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ gửi duyệt (mặc định lấy theo tài khoản đăng nhập 'baotq').",
    )


@tool("submit_request_doc_approval", args_schema=SubmitRequestDocInput)
async def submit_request_doc_approval(
    doc_identifier: str,
    user_name: Optional[str] = None,
) -> str:
    """Gửi phê duyệt Tờ trình Mua sắm đang ở trạng thái Lưu Nháp trên hệ thống gAMSPro.

    Dùng tool này khi người dùng yêu cầu gửi phê duyệt một tờ trình đã có trên hệ thống
    (ví dụ: 'Gửi phê duyệt tờ trình PUR/2026/000065 giúp tôi', 'Trình duyệt tờ trình vừa tạo').
    """
    try:
        uname = (user_name or "").strip() or "baotq"
        clean_id = (doc_identifier or "").strip()

        if not clean_id:
            return "Vui lòng cung cấp số Tờ trình mua sắm cần gửi phê duyệt."

        resolved_req_id = clean_id
        doc_code = clean_id

        # 1. Tìm REQ_ID qua search nếu đầu vào là PUR/...
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
                resolved_req_id = items[0].get("reQ_ID", clean_id)
                doc_code = items[0].get("reQ_CODE", clean_id)
            else:
                return f"Không tìm thấy Tờ trình '{clean_id}' trên hệ thống gAMSPro để gửi phê duyệt."

        # 2. Gọi API TR_REQUEST_DOC_SendApp
        params = {
            "REQ_ID": resolved_req_id,
            "PROCESS_ID": "APPNEW",
            "TLNAME": uname,
            "MAKER_ID": uname,
        }

        res = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_SendApp", params=params)
        res_data = res.get("result", {}) if isinstance(res, dict) else {}
        result_code = str(res_data.get("Result", ""))

        relative_url = f"/app/admin/request-doc-view;id={resolved_req_id}"

        if result_code == "0":
            return (
                f"✅ **GỬI PHÊ DUYỆT TỜ TRÌNH THÀNH CÔNG!**\n\n"
                f"- **Số Tờ trình:** 📄 `{doc_code}`\n"
                f"- **Mã hệ thống:** `{resolved_req_id}`\n"
                f"- **Trạng thái mới:** ⏳ **Đã gửi phê duyệt** (Đang chờ cấp quản lý ký duyệt số)\n\n"
                f"👉 **Theo dõi hồ sơ:** [{doc_code}]({relative_url})\n\n"
                f"Hồ sơ đã được chuyển tiếp đến cấp thẩm quyền. Bất kỳ lúc nào, anh chỉ cần hỏi tôi để kiểm tra tiến độ phê duyệt nhé!"
            )
        else:
            err_desc = res_data.get("ErrorDesc") or res_data.get("errorDesc") or "Hệ thống từ chối do chưa đủ điều kiện gửi duyệt."
            return (
                f"⚠️ **CHƯA THỂ GỬI PHÊ DUYỆT TỜ TRÌNH {doc_code}:**\n\n"
                f"Lý do từ hệ thống gAMSPro:\n"
                f"> {err_desc}\n\n"
                f"👉 Anh vui lòng truy cập [{doc_code}]({relative_url}) trên giao diện web để kiểm tra và hoàn thiện các mục theo yêu cầu."
            )

    except Exception as e:
        logger.exception("Error sending approval for request doc")
        return f"Lỗi kết nối gAMSPro khi gửi phê duyệt Tờ trình: {e}"
