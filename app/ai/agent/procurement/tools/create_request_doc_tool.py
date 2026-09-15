import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.ai.agent.procurement.tools.client import post_backend_api
from app.core.user_context import get_current_user_name

logger = logging.getLogger(__name__)


class CreateRequestDocInput(BaseModel):
    title: str = Field(
        description="Tiêu đề / Tên Tờ trình Mua sắm (ví dụ: 'Mua sắm máy in văn phòng'). Bắt buộc.",
    )
    estimated_amount: float = Field(
        description="Tổng số tiền đề xuất dự kiến (VNĐ) (ví dụ: 15000000). Bắt buộc phải có và > 0.",
    )
    plan_code: Optional[str] = Field(
        default="",
        description="Mã Kế hoạch ngân sách liên kết (ví dụ: '.../TTr-...'). Không bắt buộc.",
    )
    description: Optional[str] = Field(
        default="",
        description="Nội dung / Lý do / Mục đích chi tiết của Tờ trình mua sắm.",
    )


@tool("create_request_doc", args_schema=CreateRequestDocInput)
async def create_request_doc(
    title: Optional[str] = None,
    estimated_amount: Optional[float] = None,
    plan_code: Optional[str] = "",
    description: Optional[str] = "",
    **kwargs,
) -> str:
    """Tạo mới Tờ trình Mua sắm (Lưu Nháp) trên hệ thống gAMSPro.

    ĐIỀU KIỆN TIÊN QUYẾT BẮT BUỘC:
    - CHỈ ĐƯỢC GỌI khi người dùng ĐÃ CUNG CẤP CỤ THỂ Số tiền đề xuất (estimated_amount > 0).
    - NẾU người dùng CHƯA NÊU RÕ SỐ TIỀN ĐỀ XUẤT (ví dụ chỉ nói 'Tạo tờ trình ABC'): TUYỆT ĐỐI KHÔNG GỌI TOOL NÀY mà phải hỏi người dùng để bổ sung số tiền.
    - Thao tác này bắt buộc người dùng phải đăng nhập phiên gAMSPro hợp lệ.
    """
    try:
        uname = get_current_user_name()
        if not uname:
            return "⚠️ Bạn chưa đăng nhập tài khoản gAMSPro. Vui lòng đăng nhập để thực hiện tạo mới tờ trình mua sắm."
        raw_title = title or kwargs.get("tieu_de") or kwargs.get("name") or ""
        clean_title = str(raw_title).strip().strip("<>").strip()
        amt_val = estimated_amount if estimated_amount is not None else (kwargs.get("tong_tien") if kwargs.get("tong_tien") is not None else kwargs.get("amount"))
        amt = float(amt_val or 0)
        raw_desc = description or kwargs.get("noi_dung") or clean_title
        content = str(raw_desc).strip().strip("<>").strip()
        raw_plan = plan_code or kwargs.get("ma_ke_hoach") or ""
        plan_code = str(raw_plan).strip().strip("<>").strip()

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
        raw_res = res.get("result", res) if isinstance(res, dict) else res
        item = {}
        if isinstance(raw_res, list) and raw_res:
            item = raw_res[0] if isinstance(raw_res[0], dict) else {}
        elif isinstance(raw_res, dict):
            item = raw_res

        result_code = str(item.get("Result") or item.get("result") or ("0" if item.get("REQ_CODE") or item.get("reQ_CODE") else "-1"))
        if result_code == "0" or item.get("REQ_CODE") or item.get("reQ_CODE") or item.get("reQ_ID"):
            req_code = item.get("REQ_CODE") or item.get("reQ_CODE") or "Mới"
            req_id = item.get("REQ_ID") or item.get("reQ_ID") or ""
            relative_url = f"/app/admin/request-doc-view;id={req_id}"

            return (
                f"✅ **TẠO MỚI TỜ TRÌNH MUA SẮM THÀNH CÔNG TRÊN GAMSPRO!**\n\n"
                f"- **Số Tờ trình:** 📄 `{req_code}`\n"
                f"- **Tiêu đề / Tên tờ trình:** **{clean_title}**\n"
                f"- **Tổng tiền đề xuất:** **{amt:,.0f} VNĐ**\n"
                f"- **Trạng thái:** ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt)\n"
                f"- **Mã hệ thống (REQ_ID):** `{req_id}`\n"
                f"- **Kế hoạch liên kết:** 📌 `{resolved_plan_code or 'Chưa liên kết'}`\n\n"
                f"👉 **Đường dẫn xem hồ sơ:** [{req_code}]({relative_url})\n\n"
                f"Anh có muốn gửi phê duyệt tờ trình này ngay bây giờ không ạ?"
            )
        else:
            err = item.get("ErrorDesc") or item.get("errorDesc") or str(res)
            return f"Không thể tạo Tờ trình trên gAMSPro do lỗi: {err}"

    except Exception as e:
        logger.exception("Error creating request doc via API")
        return f"Lỗi kết nối gAMSPro khi tạo Tờ trình mua sắm: {e}"
