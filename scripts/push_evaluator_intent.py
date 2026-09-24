import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from langfuse import Langfuse

# 1. Tự động load file .env từ thư mục gốc dev_llm_service
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 2. Khởi tạo Langfuse client
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-096410ce-6fd7-4b75-a825-0d3c1a3f86e1"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-c5257d45-24cd-471d-8177-7ca18feb4838"),
    host=os.getenv("LANGFUSE_HOST", "http://localhost:3000")
)

# Cấu hình danh sách các Agent và đường dẫn eval/cases/ tương ứng
AGENT_DATASETS = {
    "supervisor": {
        "dataset_name": "bvbank-supervisor-dataset",
        "description": "Dataset đánh giá Intent Classifier / Routing cho hệ thống BVBank AI Assistant",
        "cases_dir": PROJECT_ROOT / "app" / "ai" / "agent" / "supervisor" / "eval" / "cases"
    },
    "agentic_rag": {
        "dataset_name": "bvbank-agentic-rag-dataset",
        "description": "Dataset đánh giá Agentic RAG tra cứu tài liệu hướng dẫn sử dụng gAMSPro",
        "cases_dir": PROJECT_ROOT / "app" / "ai" / "agent" / "agentic_rag" / "eval" / "cases"
    },
    "faq": {
        "dataset_name": "bvbank-faq-dataset",
        "description": "Dataset đánh giá FAQ Agent câu hỏi thường gặp ngân hàng BVBank",
        "cases_dir": PROJECT_ROOT / "app" / "ai" / "agent" / "faq" / "eval" / "cases"
    },
    "procurement": {
        "dataset_name": "bvbank-procurement-dataset",
        "description": "Dataset đánh giá Procurement Agent tra cứu tờ trình mua sắm gAMSPro",
        "cases_dir": PROJECT_ROOT / "app" / "ai" / "agent" / "procurement" / "eval" / "cases"
    }
}


def load_cases_from_dir(cases_dir: Path) -> list[dict]:
    """Đọc tất cả các file JSON trong thư mục eval/cases/"""
    if not cases_dir.exists():
        print(f"⚠️ Thư mục không tồn tại: {cases_dir}")
        return []

    all_cases = []
    json_files = sorted(cases_dir.glob("*.json"))
    for jf in json_files:
        print(f"  📄 Đang đọc file: {jf.relative_to(PROJECT_ROOT)}")
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_cases.extend(data)
                elif isinstance(data, dict):
                    all_cases.append(data)
        except Exception as e:
            print(f"  ❌ Lỗi khi đọc file {jf.name}: {e}")

    return all_cases


def push_dataset_for_agent(agent_key: str):
    config = AGENT_DATASETS.get(agent_key)
    if not config:
        print(f"❌ Không tìm thấy cấu hình cho agent: '{agent_key}'")
        return

    dataset_name = config["dataset_name"]
    description = config["description"]
    cases_dir = config["cases_dir"]

    print(f"\n=======================================================")
    print(f"🚀 Bắt đầu push dataset cho Agent: [{agent_key.upper()}]")
    print(f"📌 Dataset Name: {dataset_name}")
    print(f"📁 Cases Directory: {cases_dir.relative_to(PROJECT_ROOT)}")
    print(f"=======================================================")

    # 1. Đọc danh sách test cases từ eval/cases/
    test_cases = load_cases_from_dir(cases_dir)
    if not test_cases:
        print(f"⚠️ Không có test case nào được tìm thấy trong {cases_dir}")
        return

    print(f"🔍 Đã tìm thấy tổng cộng: {len(test_cases)} test cases.")

    # 2. Tạo hoặc lấy Dataset trên Langfuse
    try:
        dataset = langfuse.create_dataset(
            name=dataset_name,
            description=f"{description} ({len(test_cases)} test cases)"
        )
        print(f"✅ Đã kết nối / tạo Langfuse Dataset: '{dataset_name}'")
    except Exception as e:
        print(f"ℹ️ Thông báo khi tạo dataset '{dataset_name}': {e}")

    # 3. Đẩy từng item lên Langfuse Dataset Item
    success_count = 0
    for idx, tc in enumerate(test_cases, 1):
        test_id = tc.get("id", f"{agent_key}_{idx:03d}")
        raw_input = tc.get("input", {})
        
        # 1. Chuẩn hóa Input variables khớp với Prompt Template trên Langfuse
        if agent_key == "supervisor":
            query_val = raw_input.get("query") or raw_input.get("user_query") or ""
            chat_history_val = raw_input.get("chat_history") or "(không có)"
            user_input = {
                "query": query_val,
                "chat_history": chat_history_val
            }
        elif agent_key in ("faq", "agentic_rag", "procurement"):
            query_val = raw_input.get("query") or raw_input.get("user_query") or ""
            user_input = {
                "query": query_val,
                "chat_history": raw_input.get("chat_history", "(không có)")
            }
        else:
            user_input = raw_input

        # 2. Chuẩn hóa Expected Output dạng Text cho Langfuse Evaluators
        if tc.get("expected_output") is not None:
            expected_output = tc["expected_output"]
        elif isinstance(tc.get("expected"), dict):
            if "target_agent" in tc["expected"]:
                expected_output = str(tc["expected"]["target_agent"])
            elif "reference_answer" in tc["expected"]:
                expected_output = str(tc["expected"]["reference_answer"])
            else:
                expected_output = str(tc["expected"])
        else:
            expected_output = str(tc.get("expected", ""))
        
        # Metadata chứa các thông tin mở rộng (tags, category, module, ...)
        metadata = {
            "test_id": test_id,
            "index": tc.get("index", idx),
            "tags": tc.get("tags", []),
            "module": tc.get("module"),
            "category": tc.get("category"),
            "difficulty": tc.get("difficulty")
        }
        # Loại bỏ các key có giá trị None trong metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        try:
            langfuse.create_dataset_item(
                dataset_name=dataset_name,
                input=user_input,
                expected_output=expected_output,
                metadata=metadata
            )
            success_count += 1
            if success_count % 10 == 0 or success_count == len(test_cases):
                print(f"  ⚡ Đã đẩy {success_count}/{len(test_cases)} cases...")
        except Exception as e:
            print(f"  ❌ Lỗi đẩy test case ID '{test_id}': {e}")

    # 4. Flush để bảo đảm toàn bộ dữ liệu đã được gửi lên server
    langfuse.flush()
    print(f"🎉 Hoàn thành! Đã đẩy thành công {success_count}/{len(test_cases)} test cases lên Langfuse Dataset: '{dataset_name}'\n")


def main():
    parser = argparse.ArgumentParser(description="Đẩy các test cases trong eval/cases/ lên Langfuse Datasets")
    parser.add_argument(
        "--agent",
        type=str,
        default="supervisor",
        choices=["supervisor", "agentic_rag", "faq", "procurement", "all"],
        help="Chọn agent cần push dataset (mặc định: 'supervisor' cho Intent Classification, hoặc 'all' cho tất cả)"
    )
    args = parser.parse_args()

    if args.agent == "all":
        for key in AGENT_DATASETS.keys():
            push_dataset_for_agent(key)
    else:
        push_dataset_for_agent(args.agent)


if __name__ == "__main__":
    main()