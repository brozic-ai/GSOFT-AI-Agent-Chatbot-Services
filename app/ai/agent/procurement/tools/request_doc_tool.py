import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache token trong bộ nhớ tạm để tránh phải login lại liên tục mỗi lần gọi tool
_TOKEN_CACHE: dict[str, str] = {"token": ""}


async def get_backend_auth_token() -> str:
    """Lấy Bearer JWT Token từ C# Backend API TokenAuth."""
    if _TOKEN_CACHE["token"]:
        return _TOKEN_CACHE["token"]

    login_url = f"{settings.NET_BACKEND_URL}/api/TokenAuth/Authenticate"
    auth_payload = {
        "userNameOrEmailAddress": "baotq",
        "password": "Gsoft@#hai0hai6",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(login_url, json=auth_payload)
        if res.status_code == 200:
            token = res.json().get("result", {}).get("accessToken", "")
            _TOKEN_CACHE["token"] = token
            return token
        else:
            logger.error(f"Failed to authenticate with C# backend: {res.text}")
            raise RuntimeError("Authentication with C# Backend failed.")


class SearchRequestDocsInput(BaseModel):
    so_to_trinh: Optional[str] = Field(
        default="",
        description="Mã số tờ trình cần tra cứu (ví dụ: 'PUR/2025/000052'). Nếu rỗng sẽ lấy danh sách tờ trình gần đây.",
    )
    user_name: Optional[str] = Field(
        default="baotq",
        description="Username người dùng đang tra cứu để phân quyền.",
    )
    type_job: Optional[str] = Field(
        default="DVKD",
        description="Loại đơn vị lập tờ trình (DVKD: Đơn vị kinh doanh, DVMS: Đơn vị mua sắm).",
    )


@tool("search_request_docs", args_schema=SearchRequestDocsInput)
async def search_request_docs(
    so_to_trinh: Optional[str] = "",
    user_name: Optional[str] = "baotq",
    type_job: Optional[str] = "DVKD",
) -> str:
    """Tra cứu danh sách hoặc thông tin chi tiết của Tờ trình Mua sắm/Nghiệp vụ trên hệ thống gAMSPro.

    Dùng tool này khi người dùng muốn:
    - Tìm kiếm tờ trình theo mã số (ví dụ: "PUR/2025/000052").
    - Tra cứu trạng thái phê duyệt của tờ trình (Đang trình / Đã duyệt / Lưu nháp).
    - Xem người khởi tạo, ngày tạo và tổng số tiền đề xuất mua sắm của tờ trình.
    """
    try:
        token = await get_backend_auth_token()
        url = f"{settings.NET_BACKEND_URL}/api/RequestDoc/TR_REQUEST_DOC_Search"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "maxResultCount": 10,
            "skipCount": 0,
            "reQ_CODE": so_to_trinh or "",
            "type": type_job or "DVKD",
            "tlnamE_USER": user_name or "baotq",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)

            # Nếu token hết hạn (401), clear cache và tự động login lại 1 lần
            if res.status_code == 401:
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
                return f"Không tìm thấy tờ trình nào khớp với mã '{so_to_trinh}'."

            # Format dữ liệu gọn gàng giúp LLM đọc hiểu dễ dàng & tiết kiệm token
            formatted_results = []
            for idx, item in enumerate(items, 1):
                amt = item.get("totaL_AMT", 0)
                amt_str = f"{amt:,.0f} VNĐ" if amt else "0 VNĐ"

                doc_info = (
                    f"{idx}. Số Tờ trình: {item.get('reQ_CODE', 'N/A')}\n"
                    f"   - Mã hệ thống: {item.get('reQ_ID', 'N/A')}\n"
                    f"   - Trạng thái duyệt: {item.get('autH_STATUS_NAME', 'Không xác định')} ({item.get('procesS_STATUS_NEXT', '')})\n"
                    f"   - Người tạo: {item.get('makeR_NAME', item.get('useR_REQUEST_NAME', 'N/A'))} ({item.get('deP_CREATE_NAME', '')})\n"
                    f"   - Đơn vị: {item.get('brancH_NAME_DVMS', item.get('brancH_DO_NAME', 'N/A'))}\n"
                    f"   - Tổng tiền đề xuất: {amt_str}\n"
                    f"   - Ngày lập: {item.get('reQ_DT', 'N/A')}\n"
                    f"   - Trích yếu / Lý do: {item.get('reQ_REASON', 'Không có')}\n"
                    f"   - Mã Kế hoạch liên kết: {item.get('pL_REQ_CODE', 'Không có')}"
                )
                formatted_results.append(doc_info)

            summary = (
                f"Tìm thấy tổng cộng {total} tờ trình. Dưới đây là thông tin chi tiết:\n\n"
                + "\n\n".join(formatted_results)
            )
            return summary

    except Exception as e:
        logger.exception("Error executing search_request_docs tool")
        return f"Lỗi hệ thống khi tra cứu tờ trình: {str(e)}"
