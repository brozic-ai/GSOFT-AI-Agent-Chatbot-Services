import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings
from app.ai.agent.procurement.tools.request_doc_tool import get_backend_auth_token

logger = logging.getLogger(__name__)


class GetPoMasterStatusInput(BaseModel):
    ma_po: Optional[str] = Field(
        default="",
        description="Mã Đơn đặt hàng PO cần tra cứu (ví dụ: 'PO-2026-001'). Để rỗng nếu lấy danh sách PO gần nhất.",
    )
    user_name: Optional[str] = Field(
        default="baotq",
        description="Username người dùng đang tra cứu.",
    )


@tool("get_po_master_status", args_schema=GetPoMasterStatusInput)
async def get_po_master_status(
    ma_po: Optional[str] = "",
    user_name: Optional[str] = "baotq",
) -> str:
    """Tra cứu Đơn đặt hàng PO (Purchase Order) và tiến độ giao hàng mua sắm trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Tra cứu tình trạng đơn đặt hàng PO theo mã PO (ví dụ: 'PO-2026-001').
    - Kiểm tra giá trị đơn hàng, Nhà cung cấp thực hiện và ngày giao hàng dự kiến.
    - Xem đơn hàng PO đã được ký duyệt hay chưa.
    """
    try:
        token = await get_backend_auth_token()
        url = f"{settings.NET_BACKEND_URL}/api/TradePoMaster/TR_PO_MASTER_Search"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "pO_CODE": ma_po or "",
            "tlnamE_USER": user_name or "baotq",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)

            if res.status_code == 401:
                from app.ai.agent.procurement.tools.request_doc_tool import _TOKEN_CACHE
                _TOKEN_CACHE["token"] = ""
                token = await get_backend_auth_token()
                headers["Authorization"] = f"Bearer {token}"
                res = await client.post(url, json=payload, headers=headers)

            if res.status_code != 200:
                return f"Lỗi từ server C# ({res.status_code}): {res.text}"

            data = res.json().get("result", {})
            items = data.get("items", [])
            total = data.get("totalCount", 0)

            if not items:
                return f"Không tìm thấy Đơn đặt hàng PO nào khớp với mã '{ma_po}'."

            formatted_results = []
            for idx, item in enumerate(items, 1):
                amt = item.get("totaL_AMT", 0)
                amt_str = f"{amt:,.0f} VNĐ" if amt else "0 VNĐ"

                info = (
                    f"{idx}. Mã Đơn hàng PO: {item.get('pO_CODE', item.get('poCode', 'N/A'))}\n"
                    f"   - Tên gói/Nội dung PO: {item.get('pO_NAME', item.get('poName', 'Không có'))}\n"
                    f"   - Trạng thái duyệt: {item.get('autH_STATUS_NAME', item.get('statusName', 'N/A'))}\n"
                    f"   - Nhà cung cấp: {item.get('suP_NAME', item.get('supplierName', 'N/A'))}\n"
                    f"   - Tổng giá trị PO: {amt_str}\n"
                    f"   - Ngày lập PO: {item.get('pO_DT', item.get('creatE_DT', 'N/A'))}\n"
                    f"   - Hạn giao hàng: {item.get('deliverY_DT', 'Chưa xác định')}"
                )
                formatted_results.append(info)

            return (
                f"Tìm thấy tổng cộng {total} Đơn hàng PO. Chi tiết:\n\n"
                + "\n\n".join(formatted_results)
            )

    except Exception as e:
        logger.exception("Error executing get_po_master_status tool")
        return f"Lỗi hệ thống khi tra cứu đơn hàng PO: {str(e)}"
