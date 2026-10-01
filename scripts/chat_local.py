"""Simple terminal client for the local chatbot SSE endpoint."""

import argparse
import json

import requests


def ask(url: str, question: str, conversation_id: int | None = None) -> None:
    event = ""
    citations: list[dict] = []
    printed_answer = False

    with requests.post(
        f"{url.rstrip('/')}/api/v1/chat/stream",
        json={
            "message": question,
            "user_id": "local-tester",
            "conversation_id": conversation_id,
        },
        headers={"X-User-Id": "local-tester"},
        stream=True,
        timeout=(5, 300),
    ) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else raw_line
            )
            if line.startswith("event: "):
                event = line[7:]
                continue
            if not line.startswith("data: "):
                continue
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            if event == "token":
                print(payload.get("text", ""), end="", flush=True)
                printed_answer = True
            elif event == "citations" and isinstance(payload, list):
                citations = payload
            elif event == "error":
                print(f"\nLỗi chatbot: {payload}")
            elif event == "chat_ended":
                break

    if printed_answer:
        print()
    if citations:
        print(f"Nguồn được trả về: {len(citations)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Thử chatbot BVBank trên máy này")
    parser.add_argument(
        "question", nargs="?", help="Một câu hỏi; bỏ trống để hỏi nhiều lần"
    )
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument(
        "--history",
        action="store_true",
        help="Tạo cuộc trò chuyện mới và giữ ngữ cảnh giữa các câu hỏi",
    )
    args = parser.parse_args()
    conversation_id = None
    if args.history:
        response = requests.post(
            f"{args.url.rstrip('/')}/api/v1/chat/conversations",
            headers={"X-User-Id": "local-tester"},
            timeout=15,
        )
        response.raise_for_status()
        conversation_id = response.json()["conversation_id"]
        print(f"Phiên chat local: {conversation_id}")

    if args.question:
        ask(args.url, args.question, conversation_id)
        return

    print("Chatbot local. Nhấn Ctrl-C hoặc nhập 'exit' để thoát.")
    try:
        while True:
            question = input("\nBạn: ").strip()
            if question.lower() in {"exit", "quit"}:
                break
            if question:
                print("Chatbot: ", end="", flush=True)
                ask(args.url, question, conversation_id)
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    main()
