import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings
from app.ai.agent.procurement.tools.request_doc_tool import get_backend_auth_token

logger = logging.getLogger(__name__)


class GetRequestDocDetailInput(BaseModel):
    req_id: str = Field(
        description="Mã định danh hệ thống (REQ_ID) của tờ trình (ví dụ: 'TRRD00000269696').",
    )
    user_name: Optional[str] = Field(
        default="baotq",
        description="Username người dùng tra cứu.",
    )


@tool("get_request_doc_detail", args_schema=GetRequestDocDetailInput)
async def get_request_doc_detail(
    req_id: str,
    user_name: Optional[str] = "baotq",
) -> str:
    """Tra cứu thông tin chi tiết đầy đủ của một Tờ trình cụ thể theo Mã REQ_ID.

    Dùng tool này khi người dùng muốn:
    - Xem chi tiết nội dung, lý do, người duyệt của một tờ trình cụ thể.
    - Kiểm tra danh sách các danh mục tài sản/vật tư đi kèm trong tờ trình đó.
    """
    try:
        token = await get_backend_auth_token()
        url = f"{settings.NET_BACKEND_URL}/api/RequestDoc/TR_REQUEST_DOC_ById"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        params = {"id": req_id, "userLogin": user_name or "baotq"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, params=params, headers=headers)

            if res.status_code != 200:
                return f"Lỗi từ server C# ({res.status_code}): {res.text}"

            item = res.json()
            if not item or not item.get("reQ_ID"):
                return f"Không tìm thấy chi tiết cho Tờ trình có REQ_ID '{req_id}'."

            amt = item.get("totaL_AMT", 0)
            amt_str = f"{amt:,.0f} VNĐ" if amt else "0 VNĐ"

            detail_info = (
                f"📋 CHI TIẾT TỜ TRÌNH: {item.get('reQ_CODE', 'N/A')}\n"
                f"- Mã hệ thống (REQ_ID): {item.get('reQ_ID')}\n"
                f"- Trạng thái duyệt: {item.get('autH_STATUS_NAME', 'N/A')} ({item.get('procesS_STATUS_NEXT', '')})\n"
                f"- Người tạo: {item.get('makeR_NAME', item.get('useR_REQUEST_NAME', 'N/A'))} - Phòng: {item.get('deP_CREATE_NAME', 'N/A')}\n"
                f"- Đơn vị: {item.get('brancH_NAME_DVMS', item.get('brancH_DO_NAME', 'N/A'))}\n"
                f"- Tổng số tiền đề xuất: {amt_str}\n"
                f"- Ngày tạo: {item.get('creatE_DT', item.get('reQ_DT', 'N/A'))}\n"
                f"- Lý do/Mục đích: {item.get('reQ_REASON', 'Không có')}\n"
                f"- Tờ trình Kế hoạch liên kết: {item.get('pL_REQ_CODE', 'Không có')}"
            )
            return detail_info

    except Exception as e:
        logger.exception("Error executing get_request_doc_detail tool")
        return f"Lỗi hệ thống khi tra cứu chi tiết tờ trình: {str(e)}"
