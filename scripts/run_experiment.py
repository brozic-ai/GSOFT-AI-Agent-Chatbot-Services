import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo import từ thư mục gốc dev_llm_service
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langfuse import Langfuse

# 1. Khởi tạo Langfuse Client
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-096410ce-6fd7-4b75-a825-0d3c1a3f86e1"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-c5257d45-24cd-471d-8177-7ca18feb4838"),
    host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
)

DATASET_NAME = "bvbank-supervisor-dataset"
PROMPT_NAME = "supervisor"

# 2. Khởi tạo mô hình ChatOpenAI
model_name = os.getenv("LLM_MODEL", "qwen3:1.7b")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
api_key = os.getenv("LLM_API_KEY", "EMPTY")

print(f"================================================================================")
print(f"🚀 Khởi tạo ChatOpenAI: Model = '{model_name}' | URL = '{base_url}'")
print(f"📥 Đang tải Prompt '{PROMPT_NAME}' từ Langfuse...")

supervisor_prompt_obj = None
prompt_version = "1"
try:
    supervisor_prompt_obj = langfuse.get_prompt(PROMPT_NAME)
    prompt_version = str(getattr(supervisor_prompt_obj, "version", "1"))
    print(f"✅ Đã tải Prompt '{PROMPT_NAME}' (Version {prompt_version}) thành công từ Langfuse!")
except Exception as ex:
    print(f"⚠️ Không thể tải prompt từ Langfuse: {ex}. Sử dụng prompt mặc định cục bộ.")

timestamp_str = datetime.now().strftime("%m%d-%H%M%S")
RUN_NAME = f"qwen3-prompt-v{prompt_version}-{timestamp_str}"
print(f"🏷️ Run Name trên Langfuse Experiments: '{RUN_NAME}'")
print(f"================================================================================\n")

local_llm = ChatOpenAI(
    model=model_name,
    base_url=base_url,
    api_key=api_key,
    temperature=0.1,
    request_timeout=60,
)

# Fallback prompt nếu không tải được từ Langfuse
SYSTEM_MD_PATH = PROJECT_ROOT / "app" / "ai" / "agent" / "supervisor" / "prompts" / "v1" / "system.md"
DEFAULT_SYSTEM_PROMPT = ""
if SYSTEM_MD_PATH.exists():
    DEFAULT_SYSTEM_PROMPT = SYSTEM_MD_PATH.read_text(encoding="utf-8")
else:
    DEFAULT_SYSTEM_PROMPT = (
        "You are an expert Intent Classifier for the BVBank AI Assistant system.\n"
        "Classify the user's query into exactly ONE of: 'faq', 'rag', 'procurement', 'fallback'.\n"
        "### OUTPUT FORMAT (STRICT JSON ONLY)\n"
        "You MUST respond with valid JSON matching this schema and NO other surrounding text or markdown formatting:\n"
        "{\n"
        '  "reasoning": "string (1 short sentence explaining why in Vietnamese analyzing the query intent BEFORE making the final decision)",\n'
        '  "intent": "faq" | "rag" | "procurement" | "fallback",\n'
        '  "query": "string (the clean search phrase)",\n'
        '  "confidence": float (between 0.85 and 1.00)\n'
        "}"
    )


def build_messages_from_prompt(user_query: str, chat_history: any) -> list[BaseMessage]:
    """Compile prompt từ Langfuse thành danh sách LangChain Messages."""
    history_text = (
        chat_history
        if isinstance(chat_history, str)
        else ("\n".join(f"{h.get('role', 'user')}: {h.get('content', '')}" for h in (chat_history or [])[-6:]) or "(không có)")
    )

    if supervisor_prompt_obj:
        try:
            compiled = supervisor_prompt_obj.compile(
                query=user_query,
                user_query=user_query,
                chat_history=history_text,
            )

            if isinstance(compiled, list):
                langchain_messages: list[BaseMessage] = []
                for m in compiled:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if role == "system":
                        langchain_messages.append(SystemMessage(content=content))
                    elif role == "user":
                        langchain_messages.append(HumanMessage(content=content))
                    elif role in ("assistant", "ai"):
                        langchain_messages.append(AIMessage(content=content))

                if len(langchain_messages) == 1 and isinstance(langchain_messages[0], SystemMessage):
                    langchain_messages.append(HumanMessage(content=user_query))

                if langchain_messages:
                    return langchain_messages

            elif isinstance(compiled, str):
                return [
                    SystemMessage(content=compiled),
                    HumanMessage(content=user_query),
                ]
        except Exception:
            pass

    return [
        SystemMessage(content=DEFAULT_SYSTEM_PROMPT),
        HumanMessage(content=f"User Query: {user_query}"),
    ]


def parse_intent(raw_text: str) -> str:
    """Trích xuất intent từ chuỗi phản hồi của LLM."""
    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw_text).strip(), flags=re.MULTILINE).strip()
    clean = clean_text.lower()

    # 1. Thử parse JSON trực tiếp sau khi loại bỏ markdown fence
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict) and "intent" in data:
            return str(data["intent"]).lower().strip()
    except Exception:
        pass

    # 2. Tìm pattern json bằng regex: "intent": "..."
    match = re.search(r'"intent"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
    if match:
        return match.group(1).lower().strip()

    # 3. Kiểm tra các từ khóa hợp lệ
    for valid_intent in ["procurement", "gamspro", "faq", "rag", "fallback"]:
        if valid_intent in clean:
            return valid_intent

    return clean


# Biến đếm tiến độ hiển thị trực quan
processed_count = 0
total_items = 0


# 3. Định nghĩa Task thực thi cho từng item
def supervisor_task(*, item, **kwargs):
    """Xử lý từng câu hỏi trong Dataset qua Prompt Supervisor và LLM."""
    global processed_count
    processed_count += 1
    current_idx = processed_count

    if isinstance(item.input, dict):
        user_query = item.input.get("query") or item.input.get("user_query") or ""
        chat_history = item.input.get("chat_history") or "(không có)"
    else:
        user_query = str(item.input)
        chat_history = "(không có)"

    # Lấy expected target
    if isinstance(item.expected_output, dict):
        exp = item.expected_output.get("target_agent") or item.expected_output.get("intent") or ""
    else:
        exp = str(item.expected_output) if item.expected_output is not None else ""
    exp = exp.strip().lower()
    if exp == "gamspro":
        exp = "rag"

    messages = build_messages_from_prompt(user_query=user_query, chat_history=chat_history)
    start_t = time.time()
    raw_res = ""
    try:
        response = local_llm.invoke(messages)
        latency_ms = (time.time() - start_t) * 1000
        raw_res = str(response.content).strip()
        predicted_intent = parse_intent(raw_res)
    except Exception as ex:
        latency_ms = (time.time() - start_t) * 1000
        predicted_intent = "error"
        raw_res = str(ex)

    if predicted_intent == "gamspro":
        predicted_intent = "rag"

    is_pass = "✅ PASS" if (predicted_intent == exp or exp in predicted_intent) else "❌ FAIL"
    total_str = f"{total_items}" if total_items > 0 else "75"
    print(f"[{current_idx:02d}/{total_str}] Query: '{user_query[:32]}...' -> Intent: '{predicted_intent}' (Expected: '{exp}') | {is_pass} ({latency_ms:.0f}ms)")

    return {
        "predicted_intent": predicted_intent,
        "raw_response": raw_res,
    }


# 4. Định nghĩa hàm Evaluator đánh giá độ chính xác (Accuracy)
def accuracy_evaluator(*, input, output, expected_output=None, **kwargs):
    """So sánh kết quả dự đoán với nhãn kỳ vọng và chấm điểm 1.0 (Pass) hoặc 0.0 (Fail)."""
    if isinstance(expected_output, dict):
        expected = expected_output.get("target_agent") or expected_output.get("intent") or ""
    else:
        expected = str(expected_output) if expected_output is not None else ""
    expected = expected.strip().lower()

    if expected == "gamspro":
        expected = "rag"

    predicted = output.get("predicted_intent", "") if isinstance(output, dict) else str(output)
    predicted = predicted.strip().lower()

    is_pass = 1.0 if predicted == expected or (expected in predicted) else 0.0

    return {
        "name": "accuracy",
        "value": is_pass,
        "comment": f"Expected: {expected} | Got: {predicted}",
    }


# 5. Tải dataset và chạy Experiment chuẩn Langfuse
print(f"📥 Đang tải dataset '{DATASET_NAME}' từ Langfuse...")
dataset = langfuse.get_dataset(DATASET_NAME)
total_items = len(dataset.items)
print(f"✅ Đã tải thành công dataset với {total_items} items.\n")

print(f"🚀 Bắt đầu thực thi Experiment '{RUN_NAME}' (Đồng bộ Real-time lên Langfuse)...\n")

result = dataset.run_experiment(
    name=f"Supervisor-{model_name}-v{prompt_version}",
    run_name=RUN_NAME,
    description=f"Evaluation of prompt '{PROMPT_NAME}' version {prompt_version} on model {model_name}",
    task=supervisor_task,
    evaluators=[accuracy_evaluator],
    max_concurrency=1,
)

# 6. Hiển thị kết quả chi tiết
print("\n" + "=" * 80)
print(result.format(include_item_results=True))
print("=" * 80)

print(f"\n🎉 Hoàn thành Experiment Run: '{RUN_NAME}'!")
print(f"🌐 Xem biểu đồ & so sánh trên Langfuse:")
print(f"   👉 {getattr(result, 'dataset_run_url', f'http://localhost:3000/datasets/{DATASET_NAME}')}")
print("=" * 80)