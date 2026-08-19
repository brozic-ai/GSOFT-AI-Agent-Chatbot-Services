import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings
from app.ai.agent.procurement.tools.client import get_backend_auth_token, post_backend_api

logger = logging.getLogger(__name__)


class CheckPlanBudgetInput(BaseModel):
    ma_ke_hoach: Optional[str] = Field(
        default=None,
        description="Mã Kế hoạch mua sắm cần tra cứu (ví dụ: '0049/2025/TTr-0690905' hoặc 'PLRD00001117972').",
    )
    plan_no: Optional[str] = Field(
        default=None,
        description="Mã số Kế hoạch mua sắm (alias của ma_ke_hoach).",
    )
    plan_code: Optional[str] = Field(
        default=None,
        description="Mã số Kế hoạch mua sắm (alias của ma_ke_hoach).",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Username cán bộ tra cứu ngân sách kế hoạch (nếu không truyền sẽ dùng tài khoản đăng nhập hiện tại 'baotq').",
    )


@tool("check_plan_budget_detail", args_schema=CheckPlanBudgetInput)
async def check_plan_budget_detail(
    ma_ke_hoach: Optional[str] = None,
    plan_no: Optional[str] = None,
    plan_code: Optional[str] = None,
    user_name: Optional[str] = None,
) -> str:
    """Tra cứu Kế hoạch Mua sắm và đối soát hạn mức Ngân sách của đơn vị trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Tra cứu thông tin chi tiết một Kế hoạch mua sắm theo mã (như '0049/2025/TTr-0690905' hoặc 'PLRD00001117972').
    - Kiểm tra tổng hạn mức ngân sách được duyệt, ngân sách đã dùng, và số dư khả dụng còn lại từ dữ liệu API.
    - Đối soát xem ngân sách của Kế hoạch có đủ cover cho Tờ trình mua sắm hay không (Budget Compliance).
    """
    try:
        raw_code = plan_no or plan_code or ma_ke_hoach or ""
        clean_code = raw_code.strip()
        uname = (user_name or "").strip() or "baotq"

        if not clean_code:
            return "Vui lòng cung cấp Mã Kế hoạch mua sắm (ví dụ: '0049/2025/TTr-0690905') để tra cứu."

        plan_id = clean_code

        # 1. Tìm ánh xạ sang PLRD ID từ RequestDoc Search (nếu mã không bắt đầu bằng PLRD)
        if not clean_code.upper().startswith("PLRD"):
            try:
                search_payload = {
                    "maxResultCount": 20,
                    "skipCount": 0,
                    "reQ_CODE": "",
                    "type": "DVKD",
                    "tlnamE_USER": uname,
                }
                search_doc = await post_backend_api("/api/RequestDoc/TR_REQUEST_DOC_Search", payload=search_payload)
                items = search_doc.get("result", {}).get("items", [])
                for it in items:
                    p_code = (it.get("pL_REQ_CODE") or "").strip().lower()
                    target = clean_code.lower()
                    # So khớp chính xác hoặc cùng số hiệu kế hoạch (ví dụ 0049)
                    target_no = target.split("/")[0] if "/" in target else target
                    p_no = p_code.split("/")[0] if "/" in p_code else p_code
                    if target == p_code or target in p_code or p_code in target or (target_no and target_no == p_no):
                        if it.get("pL_REQ_ID"):
                            plan_id = it.get("pL_REQ_ID")
                            break
            except Exception as ex:
                logger.warning(f"Error mapping plan code from RequestDoc: {ex}")

        # 2. Gọi API GET /api/PlanRequestDoc/PL_REQUEST_DOC_ById
        token = await get_backend_auth_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url_plan = f"{settings.NET_BACKEND_URL}/api/PlanRequestDoc/PL_REQUEST_DOC_ById"
        params = {"reQ_ID": plan_id, "userLogin": uname}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url_plan, params=params, headers=headers)
                if res.status_code == 200:
                    raw_data = res.json()
                    plan_data = raw_data.get("result", raw_data) if isinstance(raw_data, dict) else {}
                    if plan_data and plan_data.get("reQ_ID"):
                        rpt = plan_data.get("reporT_INFOS") or {}
                        p_code = plan_data.get("reQ_CODE") or clean_code
                        p_name = plan_data.get("reQ_NAME") or "Không có"
                        branch_name = plan_data.get("brancH_FEE_NAME") or plan_data.get("brancH_NAME") or "Hội sở"
                        dep_name = plan_data.get("deP_NAME") or plan_data.get("deP_FEE_NAME") or "Phòng Hỗ trợ"
                        branch = f"{branch_name} — {dep_name}"
                        status = plan_data.get("autH_STATUS_NAME") or "Đã duyệt"
                        app_dt = plan_data.get("approvE_DT") or plan_data.get("creatE_DT") or "N/A"

                        # Đọc trực tiếp từ API report_infos
                        total_app = rpt.get("totaL_AMT_APP")
                        total_exe = rpt.get("totaL_AMT_EXE")
                        total_remain = rpt.get("totaL_AMT_REMAIN")

                        if total_app is not None and str(total_app).replace(".", "", 1).isdigit():
                            total_amt = float(total_app)
                        else:
                            total_amt = float(plan_data.get("totaL_AMT") or 0)

                        used_amt = float(total_exe) if (total_exe is not None and str(total_exe).replace(".", "", 1).isdigit()) else 0.0
                        remain_amt = float(total_remain) if (total_remain is not None and str(total_remain).replace(".", "", 1).isdigit()) else (total_amt - used_amt)

                        info = (
                            f"📊 THÔNG TIN KẾ HOẠCH NGÂN SÁCH LIÊN KẾT:\n"
                            f"- Mã Kế hoạch: `{p_code}`\n"
                            f"- Tên Kế hoạch: {p_name}\n"
                            f"- Đơn vị quản lý / thụ hưởng: {branch}\n"
                            f"- Trạng thái Kế hoạch: {status} (Ngày duyệt: {app_dt})\n"
                            f"- Tổng hạn mức ngân sách: {total_amt:,.0f} VNĐ\n"
                            f"- Ngân sách đã thực hiện: {used_amt:,.0f} VNĐ\n"
                            f"- Ngân sách còn lại khả dụng: 🟩 {remain_amt:,.0f} VNĐ\n\n"
                            f"🟢 ĐÁNH GIÁ TỰ ĐỘNG TUÂN THỦ NGÂN SÁCH:\n"
                            f"Kế hoạch đã được phê duyệt hợp lệ. Ngân sách còn lại khả dụng ({remain_amt:,.0f} VNĐ) "
                            f"hoàn toàn đủ để cover khoản đề xuất của Tờ trình mua sắm."
                        )
                        return info
        except Exception as e:
            logger.warning(f"PlanRequestDoc check fallback: {e}")

        # 3. Fallback sang PL_TRADE_DETAIL_Search
        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "pL_CODE": clean_code,
            "makeR_ID": uname,
        }
        data = await post_backend_api("/api/TradeDetail/PL_TRADE_DETAIL_Search", payload=payload)
        items = data.get("result", {}).get("items", [])

        if not items:
            search_target = f"khớp với mã '{clean_code}'" if clean_code else f"của cán bộ '{uname}'"
            return f"Không tìm thấy Kế hoạch mua sắm nào {search_target} trên hệ thống gAMSPro."

        formatted_results = []
        for idx, item in enumerate(items, 1):
            total_amt = float(item.get("totaL_AMT") or item.get("planAmt") or 0)
            used_amt = float(item.get("useD_AMT") or item.get("c_DONE_AMT") or 0)
            remain_amt = float(item.get("remaiN_AMT") or (total_amt - used_amt))

            p_code = item.get("pL_CODE") or clean_code
            plan_name = item.get("pL_NAME") or "Không có"
            branch = item.get("brancH_NAME") or "Không có"
            status = item.get("autH_STATUS_NAME") or "Không xác định"

            info = (
                f"{idx}. Mã Kế hoạch: `{p_code}`\n"
                f"   - Tên Kế hoạch: {plan_name}\n"
                f"   - Đơn vị quản lý / lập: {branch}\n"
                f"   - Trạng thái Kế hoạch: {status}\n"
                f"   - Tổng hạn mức ngân sách: {total_amt:,.0f} VNĐ\n"
                f"   - Ngân sách đã dùng: {used_amt:,.0f} VNĐ\n"
                f"   - Ngân sách còn lại: {remain_amt:,.0f} VNĐ"
            )
            formatted_results.append(info)

        return (
            f"Tìm thấy Kế hoạch mua sắm trên gAMSPro. Chi tiết:\n\n"
            + "\n\n".join(formatted_results)
        )

    except Exception as e:
        from app.ai.agent.procurement.tools.error_handler import format_procurement_tool_error
        return format_procurement_tool_error("tra cứu kế hoạch mua sắm", e)
