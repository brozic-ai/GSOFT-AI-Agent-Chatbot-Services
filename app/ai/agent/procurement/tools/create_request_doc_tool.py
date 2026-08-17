import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api

logger = logging.getLogger(__name__)


class CreateRequestDocInput(BaseModel):
    tieu_de: str = Field(
        description="Tiêu đề / Tên Tờ trình Mua sắm (ví dụ: 'Mua sắm máy in văn phòng phục vụ Phòng Hỗ trợ'). Bắt buộc.",
    )
    tong_tien: Optional[float] = Field(
        default=None,
        description="Tổng số tiền đề xuất dự kiến (VNĐ) (ví dụ: 15000000). BẮT BUỘC PHẢI CÓ. Nếu người dùng chưa nêu rõ số tiền trong hội thoại, TUYỆT ĐỐI KHÔNG ĐƯỢC GỌI TOOL NÀY.",
    )
    noi_dung: Optional[str] = Field(
        default="",
        description="Nội dung / Lý do / Mục đích chi tiết của Tờ trình mua sắm.",
    )
    ma_ke_hoach: Optional[str] = Field(
        default="",
        description="Mã Kế hoạch ngân sách liên kết (ví dụ: '0049/2025/TTr-0690905' hoặc '0030/2025/TTr-0690905').",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ lập tờ trình (mặc định lấy theo tài khoản 'baotq').",
    )


@tool("create_request_doc", args_schema=CreateRequestDocInput)
async def create_request_doc(
    tieu_de: str,
    tong_tien: Optional[float] = None,
    noi_dung: Optional[str] = "",
    ma_ke_hoach: Optional[str] = "",
    user_name: Optional[str] = None,
) -> str:
    """Tạo mới Tờ trình Mua sắm (Lưu Nháp) trên hệ thống gAMSPro.

    ĐIỀU KIỆN TIÊN QUYẾT BẮT BUỘC:
    - CHỈ ĐƯỢC GỌI khi người dùng ĐÃ CUNG CẤP CỤ THỂ Số tiền đề xuất (tong_tien > 0).
    - NẾU người dùng CHƯA NÊU RÕ SỐ TIỀN ĐỀ XUẤT (ví dụ chỉ nói 'Tạo tờ trình ABC'): TUYỆT ĐỐI KHÔNG GỌI TOOL NÀY mà phải hỏi người dùng để bổ sung số tiền.
    """
    try:
        uname = (user_name or "").strip() or "baotq"
        clean_title = (tieu_de or "").strip()
        amt = float(tong_tien or 0)
        content = (noi_dung or clean_title).strip()
        plan_code = (ma_ke_hoach or "").strip()

        if not clean_title:
            return "Chưa thể tạo Tờ trình: Thiếu Tiêu đề Tờ trình mua sắm."
        if amt <= 0:
            return "Chưa thể tạo Tờ trình: Tổng số tiền đề xuất phải lớn hơn 0 VNĐ."

        # 1. Tìm ánh xạ sang PL_REQ_ID nếu có mã kế hoạch
        pl_req_id = ""
        resolved_plan_code = plan_code
        if plan_code:
            try:
                search_doc = await post_backend_api(
                    "/api/RequestDoc/TR_REQUEST_DOC_Search",
                    payload={"maxResultCount": 20, "skipCount": 0, "reQ_CODE": "", "type": "DVKD", "tlnamE_USER": uname}
                )
                items = search_doc.get("result", {}).get("items", [])
                target = plan_code.lower()
                target_no = target.split("/")[0] if "/" in target else target
                for it in items:
                    p_code = (it.get("pL_REQ_CODE") or "").strip().lower()
                    p_no = p_code.split("/")[0] if "/" in p_code else p_code
                    if target == p_code or (target_no and target_no == p_no):
                        pl_req_id = it.get("pL_REQ_ID") or ""
                        resolved_plan_code = it.get("pL_REQ_CODE") or plan_code
                        break
            except Exception as ex:
                logger.warning(f"Error resolving plan id: {ex}")

        now_iso = datetime.now().isoformat()

        # 2. Chuẩn bị chi tiết hàng hóa mặc định
        dt_item = {
            "description": clean_title,
            "uniT_ID": "CMU000000000002",
            "uniT_NAME": "Cái",
            "quantity": 1,
            "price": amt,
            "totaL_AMT": amt,
            "pricE_ETM": amt,
            "totaL_AMT_ETM": amt,
            "exchangE_RATE": 1.0,
            "taxes": 0.0,
            "reQ_DT": now_iso,
            "traN_TYPE_ID": "TRN0000000009",
            "currency": "VND",
            "recorD_STATUS": "1",
            "makeR_ID": uname,
        }

        # 3. Payload tạo mới tờ trình
        payload = {
            "reQ_NAME": clean_title,
            "reQ_CONTENT": content,
            "reQ_REASON": content,
            "totaL_AMT": amt,
            "pL_REQ_ID": pl_req_id,
            "pL_REQ_CODE": resolved_plan_code,
            "makeR_ID": uname,
            "tlnamE_USER": uname,
            "autH_STATUS": "U",
            "recorD_STATUS": "1",
            "brancH_CREATE": "0690905",
            "brancH_DO": "0690905",
            "deP_CREATE": "0690905",
            "reQ_DT": now_iso,
            "creatE_DT": now_iso,
            "type": "DVKD",
            "tR_REQUEST_DOC_DT": [dt_item],
            "tR_REQUEST_DOC_PL_DT": [],
            "tR_REQUEST_DOC_FILE": [],
            "tR_REQ_DOC_TEMPLATE_REQUEST_DOCs": []
        }

        res = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Ins", payload=payload)
        items = res.get("result", []) if isinstance(res, dict) else []

        if items and str(items[0].get("Result")) == "0":
            req_code = items[0].get("REQ_CODE") or "Mới"
            req_id = items[0].get("REQ_ID") or ""
            relative_url = f"/app/admin/request-doc-view;id={req_id}"

            return (
                f"✅ **TẠO TỜ TRÌNH THÀNH CÔNG TRÊN GAMS PRO!**\n\n"
                f"- **Số Tờ trình:** 📄 `{req_code}`\n"
                f"- **Mã hệ thống (REQ_ID):** `{req_id}`\n"
                f"- **Tiêu đề:** {clean_title}\n"
                f"- **Tổng tiền đề xuất:** {amt:,.0f} VNĐ\n"
                f"- **Trạng thái:** ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt)\n"
                f"- **Kế hoạch liên kết:** 📌 `{resolved_plan_code or 'Chưa liên kết'}`\n\n"
                f"👉 **Đường dẫn xem hồ sơ:** [{req_code}]({relative_url})\n\n"
                f"Anh có muốn gửi phê duyệt tờ trình này ngay bây giờ không ạ?"
            )
        else:
            err = items[0].get("ErrorDesc") if items else str(res)
            return f"Không thể tạo Tờ trình trên gAMSPro do lỗi: {err}"

    except Exception as e:
        logger.exception("Error creating request doc via API")
        return f"Lỗi kết nối gAMSPro khi tạo Tờ trình mua sắm: {e}"
