import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.ai.agent.procurement.prompts.registry import get_procurement_messages, get_system_prompt
from app.ai.agent.procurement.state import ProcurementState
from app.core.user_context import get_resolved_user_name
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

# Từ điển ánh xạ tên trường thiếu sang nhãn tiếng Việt thân thiện
MISSING_FIELD_LABELS: Dict[str, str] = {
    "estimated_amount": "Tổng số tiền đề xuất (VNĐ)",
    "tong_tien": "Tổng số tiền đề xuất (VNĐ)",
    "title": "Tiêu đề / Mục đích mua sắm",
    "tieu_de": "Tiêu đề / Mục đích mua sắm",
    "plan_code": "Mã Kế hoạch ngân sách liên kết",
    "ma_ke_hoach": "Mã Kế hoạch ngân sách liên kết",
    "doc_identifier": "Số Tờ trình mua sắm (ví dụ: PUR/...)",
    "so_to_trinh": "Số Tờ trình mua sắm (ví dụ: PUR/...)",
    "doc_id": "Số Tờ trình mua sắm",
    "ma_po": "Mã Đơn đặt hàng PO (ví dụ: PO...)",
    "po_code": "Mã Đơn đặt hàng PO",
}


def _extract_json_payload(raw_text: str) -> Optional[Any]:
    """Trích xuất và parse JSON an toàn từ phản hồi LLM."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()

    # 1. Bóc tách code fence markdown (```json ... ``` hoặc ``` ... ```)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # 2. Thử parse trực tiếp
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 3. Trích xuất khoảng JSON array [...] hoặc object {...}
    array_match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except Exception:
            pass

    obj_match = re.search(r"\{\s*\"type\"\s*:.*\}", cleaned, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except Exception:
            pass

    return None


def _clean_arg_str(val: Any) -> str:
    """Loại bỏ khoảng trắng thừa và cặp ngoặc nhọn <...> nếu LLM copy từ placeholder."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.startswith("<") and s.endswith(">") and len(s) > 1:
        s = s[1:-1].strip()
    return s.strip("<>").strip()


def _normalize_tool_args(tool_name: str, raw_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hóa tham số gọi Tool về DUY NHẤT một bộ tham số chuẩn (Canonical Arguments).
    - Ánh xạ từ các alias (tiếng Anh/Việt) về đúng 1 tên tham số duy nhất theo schema.
    - Làm sạch các ký tự bao quanh như ngoặc nhọn <...> và khoảng trắng thừa.
    - Tuyệt đối không sinh nhiều tên tham số trùng lặp trong một lần gọi tool.
    """
    args = dict(raw_args) if isinstance(raw_args, dict) else {}

    if tool_name == "create_request_doc":
        raw_title = args.get("title") or args.get("tieu_de") or args.get("name")
        raw_amt = args.get("estimated_amount") if args.get("estimated_amount") is not None else (
            args.get("tong_tien") if args.get("tong_tien") is not None else args.get("amount")
        )
        raw_plan = args.get("plan_code") or args.get("ma_ke_hoach") or args.get("plan_no")
        raw_desc = args.get("description") or args.get("noi_dung") or args.get("ly_do")

        title_val = _clean_arg_str(raw_title)
        plan_val = _clean_arg_str(raw_plan)
        desc_val = _clean_arg_str(raw_desc)

        amt_val = None
        if raw_amt is not None:
            try:
                amt_clean = _clean_arg_str(raw_amt).replace(",", "").replace("VND", "").replace("VNĐ", "").replace("vnd", "").strip()
                amt_val = float(amt_clean)
            except Exception:
                amt_val = raw_amt

        normalized: Dict[str, Any] = {}
        if title_val:
            normalized["title"] = title_val
        if amt_val is not None:
            normalized["estimated_amount"] = amt_val
        if plan_val:
            normalized["plan_code"] = plan_val
        if desc_val:
            normalized["description"] = desc_val
        return normalized

    if tool_name in ("get_request_doc_detail", "submit_request_doc_approval"):
        raw_id = (
            args.get("doc_id")
            or args.get("doc_identifier")
            or args.get("req_id")
            or args.get("so_to_trinh")
            or args.get("request_id")
            or args.get("doc_no")
            or args.get("id")
        )
        clean_id = _clean_arg_str(raw_id)
        if clean_id:
            return {"doc_id": clean_id}
        return {}

    if tool_name == "search_request_docs":
        raw_code = (
            args.get("doc_code")
            or args.get("so_to_trinh")
            or args.get("doc_identifier")
            or args.get("ma_to_trinh")
        )
        raw_status = (
            args.get("status")
            or args.get("status_filter")
            or args.get("trang_thai")
            or args.get("status_name")
        )

        clean_code = _clean_arg_str(raw_code)
        clean_status = _clean_arg_str(raw_status)

        normalized = {
            "page": int(args.get("page", 1)),
            "page_size": 10,
        }
        if clean_code:
            normalized["doc_code"] = clean_code
        if clean_status:
            if clean_status.lower() not in ("gần đây", "mới nhất", "recent", "all", "tất cả", "gần", "danh sách"):
                normalized["status"] = clean_status
        return normalized

    if tool_name == "check_plan_budget_detail":
        raw_plan = (
            args.get("plan_code")
            or args.get("ma_ke_hoach")
            or args.get("plan_no")
            or args.get("plan_id")
        )
        clean_plan = _clean_arg_str(raw_plan)
        if clean_plan:
            return {"plan_code": clean_plan}
        return {}

    if tool_name == "get_po_master_status":
        raw_po = (
            args.get("po_code")
            or args.get("ma_po")
            or args.get("po_no")
            or args.get("doc_no")
        )
        clean_po = _clean_arg_str(raw_po)
        if clean_po:
            return {"po_code": clean_po}
        return {}

    return {k: _clean_arg_str(v) if isinstance(v, str) else v for k, v in args.items()}


async def router_node(state: ProcurementState) -> Dict[str, Any]:
    """
    Stage 1: Router Node cho Procurement Pipeline.
    - Nhận query và chat history.
    - Áp dụng Router System Prompt từ Langfuse (định dạng Output Contract JSON).
    - Parse JSON Output Contract:
      + Nếu là 'tool_call': Chuyển thành AIMessage với tool_calls để ToolNode thực thi.
      + Nếu là 'need_info': Sinh câu hỏi làm rõ thân thiện và dừng turn (không gọi tool).
      + Nếu là 'direct_answer' / plain text: Trả về trực tiếp cho người dùng.
    """
    messages = list(state.get("messages", [])) if isinstance(state, dict) else list(state.messages)

    # 1. Định vị HumanMessage cuối cùng (lượt hiện tại)
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    user_query = str(messages[last_human_idx].content) if last_human_idx != -1 else ""

    # 2. Xây dựng chat_history từ các tin nhắn trước HumanMessage cuối
    history_messages = messages[:last_human_idx] if last_human_idx > 0 else []
    chat_history = []
    for m in history_messages:
        if isinstance(m, HumanMessage):
            chat_history.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage) and m.content:
            chat_history.append({"role": "assistant", "content": str(m.content)})

    # 3. Nạp và compile Chat Prompt 'procurement' từ Langfuse (với các biến query, chat_history)
    router_messages = get_procurement_messages(query=user_query, chat_history=chat_history)

    # 4. Bổ sung ngữ cảnh cán bộ đang đăng nhập vào system prompt nếu có
    uname = state.get("user_name") or get_resolved_user_name()
    if uname and router_messages:
        if isinstance(router_messages[0], SystemMessage):
            router_messages[0] = SystemMessage(
                content=router_messages[0].content + f"\n\nNgữ cảnh cán bộ đang đăng nhập phiên hiện tại: {uname}"
            )

    # 5. Thực thi Router LLM (deterministic với temperature=0.0)
    llm = get_chat_model(temperature=0.0)
    response = await llm.ainvoke(router_messages)
    raw_content = str(response.content).strip() if response.content else ""

    logger.info("[PROCUREMENT-ROUTER] LLM Raw Output: %s", raw_content)

    # 4. Kiểm tra xem LLM có sinh native tool_calls không
    if hasattr(response, "tool_calls") and response.tool_calls:
        normalized_calls = []
        for tc in response.tool_calls:
            t_name = tc.get("name")
            t_args = _normalize_tool_args(t_name, tc.get("args") or {})
            normalized_calls.append({
                "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "name": t_name,
                "args": t_args,
            })
        return {
            "messages": [AIMessage(content="", tool_calls=normalized_calls)],
            "route_type": "tool_call",
        }

    # 5. Phân tích Output Contract dạng JSON
    parsed = _extract_json_payload(raw_content)
    if parsed is not None:
        items = parsed if isinstance(parsed, list) else [parsed]
        tool_calls = []
        all_missing = []

        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "need_info":
                missing = item.get("missing", [])
                if isinstance(missing, list):
                    all_missing.extend(missing)
                elif isinstance(missing, str):
                    all_missing.append(missing)

            elif item_type == "tool_call":
                t_name = item.get("tool")
                if t_name:
                    t_args = _normalize_tool_args(t_name, item.get("args") or {})
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "name": t_name,
                        "args": t_args,
                    })

            elif item_type == "direct_answer":
                direct_msg = item.get("content") or item.get("message") or ""
                if direct_msg:
                    return {
                        "messages": [AIMessage(content=direct_msg)],
                        "route_type": "direct_answer",
                    }

        # Nếu phát hiện need_info và không có tool_call khả thi
        if all_missing and not tool_calls:
            missing_labels = [MISSING_FIELD_LABELS.get(f, f) for f in set(all_missing)]
            missing_str = ", ".join([f"**{m}**" for m in missing_labels])
            prompt_user_msg = (
                f"Dạ, để tôi có thể hỗ trợ Anh/Chị xử lý yêu cầu tạo Tờ trình mua sắm, "
                f"Anh/Chị vui lòng cung cấp thêm thông tin về {missing_str} nhé."
            )
            return {
                "messages": [AIMessage(content=prompt_user_msg)],
                "route_type": "need_info",
                "missing_fields": all_missing,
            }

        # Nếu có các lệnh gọi tool hợp lệ
        if tool_calls:
            return {
                "messages": [AIMessage(content="", tool_calls=tool_calls)],
                "route_type": "tool_call",
            }

    # 6. Fallback: Nếu không phải JSON hoặc là câu trả lời giao tiếp thông thường
    return {
        "messages": [AIMessage(content=raw_content or "Dạ, tôi có thể hỗ trợ gì cho Anh/Chị về quy trình Mua sắm gAMSPro ạ?")],
        "route_type": "direct_answer",
    }
