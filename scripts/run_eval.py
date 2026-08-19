"""Chạy eval cho agent chỉ định.

Cách dùng:
    uv run python scripts/run_eval.py supervisor
    uv run python scripts/run_eval.py procurement
    uv run python scripts/run_eval.py gamspro
    uv run python scripts/run_eval.py faq
    uv run python scripts/run_eval.py --all

Thêm agent mới: thêm 1 dòng vào _AGENT_ENTRYPOINTS bên dưới, trỏ tới hàm
async nhận dict input -> dict output (chính là node/graph thật của agent,
KHÔNG mock) — không cần đụng gì tới app/eval/.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: F401 (load .env & LangSmith tracing envs)
from app.ai.eval.report import print_report, save_report_json
from app.ai.eval.runner import run_eval

_AGENTS_ROOT = PROJECT_ROOT / "app" / "ai" / "agent"


async def _supervisor_entrypoint(input_: dict[str, Any]) -> dict[str, Any]:
    from app.ai.agent.supervisor.graph.graph import supervisor_graph

    case_id = input_.get("_eval_case_id") or input_.get("case_id") or "eval"
    case_idx = input_.get("_eval_case_index")
    run_name = (
        f"Supervisor Test #{case_idx:02d} ({case_id})"
        if case_idx
        else f"Supervisor Agent [{case_id}]"
    )
    config = {
        "run_name": run_name,
        "tags": ["eval", "supervisor", f"case:{case_id}"],
        "metadata": {"case_id": case_id, "case_index": case_idx},
    }
    result = await supervisor_graph.ainvoke(state, config=config)
    route_obj = result.get("route")

    if hasattr(route_obj, "intent"):
        target_agent = (
            route_obj.intent.value
            if hasattr(route_obj.intent, "value")
            else str(route_obj.intent)
        )
        confidence = float(getattr(route_obj, "confidence", 1.0))
        reasoning = str(getattr(route_obj, "reasoning", ""))
    elif isinstance(route_obj, dict):
        target_agent = route_obj.get("intent", "fallback")
        if hasattr(target_agent, "value"):
            target_agent = target_agent.value
        confidence = float(route_obj.get("confidence", 1.0))
        reasoning = str(route_obj.get("reasoning", ""))
    else:
        target_agent = str(route_obj)
        confidence = 1.0
        reasoning = ""

    return {
        "target_agent": target_agent,
        "confidence": confidence,
        "reasoning": reasoning,
    }


async def _faq_entrypoint(input_: dict[str, Any]) -> dict[str, Any]:
    # TODO: thay bằng entrypoint thật của faq agent khi có (graph/builder.py::faq_node).
    from app.ai.agent.faq.graph.builder import faq_node  # type: ignore

    state = {"messages": [], "user_query": input_["user_query"]}
    result = await faq_node(state)
    return {"final_answer": result.get("final_answer", "")}


async def _procurement_entrypoint(input_: dict[str, Any]) -> dict[str, Any]:
    """Entrypoint thực thi Procurement Agent (gAMSPro) từ graph thật."""
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
    from app.ai.agent.procurement.graph.graph import procurement_graph

    # 1. Chuyển đổi chat_history sang danh sách BaseMessage
    messages: list[BaseMessage] = []
    chat_history = input_.get("chat_history", [])
    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "human"):
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            messages.append(AIMessage(content=content))

    # 2. Thêm tin nhắn câu hỏi hiện tại
    user_query = input_.get("user_query", "")
    if user_query:
        messages.append(HumanMessage(content=user_query))

    state = {
        "messages": messages,
        "user_name": input_.get("user_name", "baotq"),
        "session_id": input_.get("session_id", "eval-procurement"),
    }

    # 3. Thực thi graph thật với run_name tùy chỉnh cho LangSmith Tracing
    case_id = input_.get("_eval_case_id") or input_.get("case_id") or "eval"
    case_idx = input_.get("_eval_case_index")
    run_name = (
        f"Procurement Test #{case_idx:02d} ({case_id})"
        if case_idx
        else f"Procurement Agent [{case_id}]"
    )
    config = {
        "run_name": run_name,
        "tags": ["eval", "procurement", f"case:{case_id}"],
        "metadata": {
            "case_id": case_id,
            "case_index": case_idx,
            "user_name": state.get("user_name"),
        },
    }

    result = await procurement_graph.ainvoke(state, config=config)
    result_messages = result.get("messages", [])

    # 4. Trích xuất final_answer và tất cả các tool_calls đã sinh ra
    final_answer = ""
    tool_calls: list[dict[str, Any]] = []

    for msg in result_messages:
        if isinstance(msg, AIMessage) or hasattr(msg, "tool_calls"):
            tcs = getattr(msg, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    # Chuyển tool_call thành dict thuần (JSON serializable)
                    tool_calls.append({
                        "name": tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                        "args": tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {}),
                    })
            if msg.content and isinstance(msg.content, str):
                final_answer = msg.content

async def _agentic_rag_entrypoint(input_: dict[str, Any]) -> dict[str, Any]:
    """Entrypoint thực thi RAG Knowledge Agent từ graph thật."""
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

    from app.ai.agent.agentic_rag.graph.graph import agentic_rag_graph
    from app.ai.agent.agentic_rag.tools.search_policy_docs_tool import set_rbac_context

    # 1. Chuyển đổi chat_history sang danh sách BaseMessage
    messages: list[BaseMessage] = []
    chat_history = input_.get("chat_history", [])
    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "human"):
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            messages.append(AIMessage(content=content))

    # 2. Thêm câu hỏi hiện tại
    user_query = input_.get("user_query", "")
    if user_query:
        messages.append(HumanMessage(content=user_query))

    # 3. Set RBAC context cho tool
    user_roles = input_.get("user_roles", "Admin,Employee")
    user_department = input_.get("user_department")
    set_rbac_context(user_roles=user_roles, user_department=user_department)

    state = {
        "messages": messages,
        "user_query": user_query,
        "session_id": input_.get("session_id", "eval-rag"),
        "user_roles": user_roles,
        "user_department": user_department,
        "documents": [],
        "citations": [],
        "is_relevant": False,
        "retry_count": 0,
        "final_answer": "",
    }

    # 4. Tracing config cho LangSmith
    case_id = input_.get("_eval_case_id") or input_.get("case_id") or "eval"
    case_idx = input_.get("_eval_case_index")
    run_name = (
        f"RAG Test #{case_idx:02d} ({case_id})"
        if case_idx
        else f"RAG Agent [{case_id}]"
    )
    config = {
        "run_name": run_name,
        "tags": ["eval", "agentic_rag", f"case:{case_id}"],
        "metadata": {
            "case_id": case_id,
            "case_index": case_idx,
            "user_roles": user_roles,
        },
    }

    result = await agentic_rag_graph.ainvoke(state, config=config)
    result_messages = result.get("messages", [])

    final_answer = result.get("final_answer", "")
    tool_calls: list[dict[str, Any]] = []

    for msg in result_messages:
        if isinstance(msg, AIMessage) or hasattr(msg, "tool_calls"):
            tcs = getattr(msg, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    tool_calls.append({
                        "name": tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                        "args": tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {}),
                    })
            if not final_answer and msg.content and isinstance(msg.content, str):
                final_answer = msg.content

    return {
        "final_answer": final_answer,
        "tool_calls": tool_calls,
        "citations": result.get("citations", []),
    }


_AGENT_ENTRYPOINTS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "supervisor": _supervisor_entrypoint,
    "faq": _faq_entrypoint,
    "procurement": _procurement_entrypoint,
    "gamspro": _procurement_entrypoint,  # gamspro chính là procurement agent
    "agentic_rag": _agentic_rag_entrypoint,
    "rag": _agentic_rag_entrypoint,
}


async def _run_one(
    agent_name: str,
    case_index: str | int | None = None,
    only_failed: bool = False,
    min_threshold: float = 0.90,
) -> bool:
    agent_eval_dir = _AGENTS_ROOT / agent_name / "eval"
    if not agent_eval_dir.exists():
        if agent_name == "gamspro":
            agent_eval_dir = _AGENTS_ROOT / "procurement" / "eval"
        elif agent_name == "rag":
            agent_eval_dir = _AGENTS_ROOT / "agentic_rag" / "eval"

    agent_fn = _AGENT_ENTRYPOINTS[agent_name]

    report = await run_eval(
        agent_name,
        agent_eval_dir,
        agent_fn,
        case_index=case_index,
        only_failed=only_failed,
    )
    passed_benchmark = print_report(report, min_pass_rate_threshold=min_threshold)
    save_report_json(
        report,
        base_dir=PROJECT_ROOT / "data" / "eval_results",
        min_pass_rate_threshold=min_threshold,
    )

    return passed_benchmark


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chạy eval cho agent chỉ định (hỗ trợ eval 1 test case cụ thể, chỉ chạy lại các test case bị lỗi, và kiểm tra ngưỡng benchmark)."
    )
    parser.add_argument(
        "agent",
        nargs="?",
        choices=list(_AGENT_ENTRYPOINTS),
        help="Tên agent (supervisor, procurement, gamspro, faq, ...)",
    )
    parser.add_argument(
        "index",
        nargs="?",
        default=None,
        help="Index hoặc ID/tag của test case cần eval (ví dụ: 1 hoặc proc_demo_001)",
    )
    parser.add_argument("--all", action="store_true", help="Chạy eval cho tất cả agent")
    parser.add_argument(
        "--failed",
        "-f",
        action="store_true",
        help="Chỉ chạy lại các test case bị FAIL trong lần chạy gần nhất",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.90,
        help="Ngưỡng Pass Rate tối thiểu để duyệt Prompt (mặc định: 0.90 tức 90%%)",
    )
    parser.add_argument(
        "--index",
        "-i",
        dest="opt_index",
        type=str,
        default=None,
        help="Index test case cần eval (ví dụ: 1)",
    )
    args = parser.parse_args()

    if not args.all and not args.agent:
        parser.error("Chỉ định tên agent hoặc dùng --all")

    target_index = args.index or args.opt_index
    targets = list(_AGENT_ENTRYPOINTS) if args.all else [args.agent]

    all_passed = True
    for name in targets:
        ok = await _run_one(
            name,
            case_index=target_index,
            only_failed=args.failed,
            min_threshold=args.threshold,
        )
        all_passed = all_passed and ok

    if not all_passed:
        raise SystemExit(1)  # để CI fail build khi eval không đạt ngưỡng benchmark


if __name__ == "__main__":
    asyncio.run(main())
