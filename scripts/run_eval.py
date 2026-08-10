"""Chạy eval cho agent chỉ định.

Cách dùng:
    uv run python scripts/run_eval.py supervisor
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
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.eval.report import print_report, save_report_json
from app.ai.eval.runner import run_eval

_AGENTS_ROOT = PROJECT_ROOT / "app" / "ai" / "agent"


async def _supervisor_entrypoint(input_: dict[str, Any]) -> dict[str, Any]:
    from app.ai.agent.supervisor.graph.graph import supervisor_graph

    state = {
        "session_id": input_.get("session_id", "eval-session"),
        "user_query": input_["user_query"],
        "chat_history": input_.get("chat_history", []),
    }
    result = await supervisor_graph.ainvoke(state)
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


_AGENT_ENTRYPOINTS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "supervisor": _supervisor_entrypoint,
    "faq": _faq_entrypoint,
}


async def _run_one(
    agent_name: str,
    case_index: str | int | None = None,
    only_failed: bool = False,
    min_threshold: float = 0.90,
) -> bool:
    agent_eval_dir = _AGENTS_ROOT / agent_name / "eval"
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
        "agent", nargs="?", choices=list(_AGENT_ENTRYPOINTS), help="Tên agent (supervisor, faq, ...)"
    )
    parser.add_argument(
        "index",
        nargs="?",
        default=None,
        help="Index hoặc ID/tag của test case cần eval (ví dụ: 31 hoặc TC_031)",
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
        help="Ngưỡng Pass Rate tối thiểu để duyệt Prompt (mặc định: 0.90 tức 90%)",
    )
    parser.add_argument(
        "--index",
        "-i",
        dest="opt_index",
        type=str,
        default=None,
        help="Index test case cần eval (ví dụ: 31)",
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
