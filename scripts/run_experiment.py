import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo import từ thư mục gốc dev_llm_service
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langfuse import Langfuse

# 1. Import hàm lấy prompt supervisor chuẩn của hệ thống
try:
    from app.ai.agent.supervisor.prompts.registry import get_supervisor_messages
except Exception as ex:
    get_supervisor_messages = None

# Đọc fallback system.md nếu cần
SYSTEM_MD_PATH = PROJECT_ROOT / "app" / "ai" / "agent" / "supervisor" / "prompts" / "v1" / "system.md"
DEFAULT_SYSTEM_PROMPT = ""
if SYSTEM_MD_PATH.exists():
    DEFAULT_SYSTEM_PROMPT = SYSTEM_MD_PATH.read_text(encoding="utf-8")
else:
    DEFAULT_SYSTEM_PROMPT = (
        "You are an expert Intent Classifier for the BVBank AI Assistant system.\n"
        "Classify the user's query into exactly ONE of: 'faq', 'rag', 'procurement', 'fallback'.\n"
        "Return ONLY a JSON object: {\"intent\": \"faq\"|\"rag\"|\"procurement\"|\"fallback\", \"confidence\": 0.95, \"reasoning\": \"...\"}"
    )

# 2. Khởi tạo Langfuse Client
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-096410ce-6fd7-4b75-a825-0d3c1a3f86e1"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-c5257d45-24cd-471d-8177-7ca18feb4838"),
    host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
)

DATASET_NAME = "bvbank-supervisor-dataset"
RUN_NAME = "qwen3-supervisor-prompt-experiment"

# 3. Khởi tạo mô hình ChatOpenAI
model_name = os.getenv("LLM_MODEL", "qwen3:1.7b")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
api_key = os.getenv("LLM_API_KEY", "EMPTY")

print(f"=======================================================")
print(f"🚀 Khởi tạo ChatOpenAI: Model = '{model_name}' | URL = '{base_url}'")
print(f"📌 Chạy Experiment với Prompt Supervisor chuẩn hệ thống")
print(f"=======================================================")

local_llm = ChatOpenAI(
    model=model_name,
    base_url=base_url,
    api_key=api_key,
    temperature=0.1,
    request_timeout=60,
)

# 4. Tải dataset từ Langfuse
print(f"📥 Đang tải dataset '{DATASET_NAME}' từ Langfuse...")
dataset = langfuse.get_dataset(DATASET_NAME)
print(f"✅ Đã tải thành công dataset với {len(dataset.items)} items.\n")


def parse_intent(raw_text: str) -> str:
    """Trích xuất intent từ chuỗi phản hồi của LLM."""
    clean = raw_text.strip().lower()

    # 1. Thử parse JSON
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict) and "intent" in data:
            return str(data["intent"]).lower().strip()
    except Exception:
        pass

    # 2. Tìm pattern json bằng regex: "intent": "..."
    match = re.search(r'"intent"\s*:\s*"([^"]+)"', raw_text, re.IGNORECASE)
    if match:
        return match.group(1).lower().strip()

    # 3. Kiểm tra các từ khóa hợp lệ
    for valid_intent in ["procurement", "gamspro", "faq", "rag", "fallback"]:
        if valid_intent in clean:
            return valid_intent

    return clean


# 5. Chạy vòng lặp kiểm thử
passed_count = 0
total_count = len(dataset.items)

for i, item in enumerate(dataset.items, start=1):
    # Lấy input query và chat history
    if isinstance(item.input, dict):
        user_query = item.input.get("query") or item.input.get("user_query") or ""
        chat_history = item.input.get("chat_history") or []
    else:
        user_query = str(item.input)
        chat_history = []

    if isinstance(chat_history, str):
        chat_history = []

    # Lấy expected target
    if isinstance(item.expected_output, dict):
        expected_target = item.expected_output.get("target_agent") or item.expected_output.get("intent") or ""
    else:
        expected_target = str(item.expected_output)
    expected_target = expected_target.strip().lower()

    # Tạo messages với Supervisor Prompt thật của hệ thống
    if get_supervisor_messages:
        messages = get_supervisor_messages(query=user_query, chat_history=chat_history)
    else:
        messages = [
            SystemMessage(content=DEFAULT_SYSTEM_PROMPT),
            HumanMessage(content=f"User Query: {user_query}"),
        ]

    try:
        response = local_llm.invoke(messages)
        raw_output = str(response.content).strip()
        predicted_intent = parse_intent(raw_output)

        # Chuẩn hóa gamspro <-> rag nếu có
        norm_pred = "rag" if predicted_intent == "gamspro" else predicted_intent
        norm_exp = "rag" if expected_target == "gamspro" else expected_target

        is_pass = 1.0 if norm_pred == norm_exp or (norm_exp in norm_pred) else 0.0
        if is_pass == 1.0:
            passed_count += 1

        # Gửi điểm số (score) lên Langfuse
        try:
            langfuse.score(
                name="accuracy",
                value=is_pass,
                comment=f"Expected: {expected_target} | Got: {predicted_intent} | Raw: {raw_output[:100]}",
                dataset_item_id=item.id if hasattr(item, "id") else None,
            )
        except Exception:
            pass

        status_icon = "✅ PASS" if is_pass else "❌ FAIL"
        print(f"[{i:02d}/{total_count}] Query: '{user_query[:35]}...' -> Intent: '{predicted_intent}' (Expected: '{expected_target}') | {status_icon}")

    except Exception as e:
        print(f"[{i:02d}/{total_count}] ⚠️ Lỗi khi chạy item: {e}")

# Flush dữ liệu lên Langfuse trước khi kết thúc
try:
    langfuse.flush()
except Exception:
    pass

accuracy = (passed_count / total_count * 100) if total_count > 0 else 0
print(f"\n=======================================================")
print(f"🎉 Hoàn thành Experiment '{RUN_NAME}'!")
print(f"📊 Độ chính xác: {passed_count}/{total_count} passed ({accuracy:.2f}%)")
print(f"🌐 Xem chi tiết trên giao diện Langfuse > Datasets > {DATASET_NAME}")
print(f"=======================================================")