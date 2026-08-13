import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings
from app.ai.agent.procurement.tools.request_doc_tool import get_backend_auth_token

logger = logging.getLogger(__name__)


class CheckPlanBudgetInput(BaseModel):
    ma_ke_hoach: Optional[str] = Field(
        default="",
        description="Mã Kế hoạch mua sắm cần tra cứu (ví dụ: 'KH-001' hoặc '0030/2025/TTr-0690905'). Để rỗng nếu lấy tất cả.",
    )
    user_name: Optional[str] = Field(
        default="baotq",
        description="Username người dùng đang tra cứu.",
    )


@tool("check_plan_budget_detail", args_schema=CheckPlanBudgetInput)
async def check_plan_budget_detail(
    ma_ke_hoach: Optional[str] = "",
    user_name: Optional[str] = "baotq",
) -> str:
    """Tra cứu Dòng Kế hoạch Mua sắm trang thiết bị/hàng hóa và ngân sách của đơn vị trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Kiểm tra danh mục vật tư/tài sản có nằm trong Kế hoạch mua sắm năm/quý hay không.
    - Tra cứu hạn mức ngân sách và tiến độ phê duyệt kế hoạch mua sắm.
    """
    try:
        token = await get_backend_auth_token()
        url = f"{settings.NET_BACKEND_URL}/api/TradeDetail/PL_TRADE_DETAIL_Search"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "pL_CODE": ma_ke_hoach or "",
            "makeR_ID": user_name or "baotq",
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
                return f"Không tìm thấy Kế hoạch mua sắm nào khớp với từ khóa '{ma_ke_hoach}'."

            formatted_results = []
            for idx, item in enumerate(items, 1):
                amt = item.get("totaL_AMT", item.get("planAmt", 0))
                amt_str = f"{amt:,.0f} VNĐ" if amt else "0 VNĐ"

                info = (
                    f"{idx}. Mã Kế hoạch: {item.get('pL_CODE', item.get('plAn_CODE', 'N/A'))}\n"
                    f"   - Tên Kế hoạch: {item.get('pL_NAME', item.get('plAn_NAME', 'N/A'))}\n"
                    f"   - Đơn vị lập: {item.get('brancH_NAME', 'N/A')}\n"
                    f"   - Trạng thái duyệt: {item.get('autH_STATUS_NAME', item.get('statusName', 'Đã duyệt'))}\n"
                    f"   - Tổng hạn mức ngân sách: {amt_str}\n"
                    f"   - Ngày lập: {item.get('creatE_DT', 'N/A')}"
                )
                formatted_results.append(info)

            return (
                f"Tìm thấy tổng cộng {total} dòng Kế hoạch mua sắm. Chi tiết:\n\n"
                + "\n\n".join(formatted_results)
            )

    except Exception as e:
        logger.exception("Error executing check_plan_budget_detail tool")
        return f"Lỗi hệ thống khi tra cứu kế hoạch mua sắm: {str(e)}"
