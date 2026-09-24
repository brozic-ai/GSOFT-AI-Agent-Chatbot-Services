"""Chạy eval cho 1 agent: đọc config.yaml (khai báo dùng metric nào) +
cases/*.json (dữ liệu test) từ app/ai/agent/<agent>/eval/, gọi agent, chấm
điểm bằng Scorer, trả về EvalReport.

Mỗi agent chỉ cần cung cấp:
  app/ai/agent/<agent>/eval/config.yaml
  app/ai/agent/<agent>/eval/cases/*.json
Phần chạy + chấm điểm dùng chung 100% từ đây.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.ai.eval.metrics import (
    ExactFieldMatchMetric,
    LatencyMetric,
    LLMJudgeMetric,
    Metric,
    MinValueMetric,
    ToolCallMatchMetric,
)
from app.ai.eval.scorer import CaseResult, EvalCase, Scorer

AgentFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# Đăng ký tên metric dùng trong config.yaml -> class tương ứng.
# Thêm metric mới ở metrics.py thì đăng ký thêm 1 dòng ở đây.
_METRIC_REGISTRY: dict[str, type[Metric]] = {
    "exact_field_match": ExactFieldMatchMetric,
    "min_value": MinValueMetric,
    "latency": LatencyMetric,
    "llm_judge": LLMJudgeMetric,
    "tool_call_match": ToolCallMatchMetric,
}


@dataclass
class EvalReport:
    agent_name: str
    case_results: list[CaseResult]
    execution_time_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        if not self.case_results:
            return 0.0
        passed = sum(1 for c in self.case_results if c.passed)
        return passed / len(self.case_results)

    @property
    def avg_score(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(c.avg_score for c in self.case_results) / len(self.case_results)


def _load_metrics(config_path: Path) -> list[Metric]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metrics: list[Metric] = []
    for entry in config.get("metrics", []):
        metric_type = entry["type"]
        params = entry.get("params", {})
        metric_cls = _METRIC_REGISTRY.get(metric_type)
        if metric_cls is None:
            raise ValueError(
                f"Metric '{metric_type}' chưa được đăng ký trong _METRIC_REGISTRY"
            )
        metrics.append(metric_cls(**params))
    return metrics


def _find_project_root(start_path: Path) -> Path:
    curr = start_path.resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return curr


def _load_cases(
    cases_dir: Path,
    target_index: str | int | None = None,
    only_failed: bool = False,
    agent_name: str | None = None,
    results_dir: Path | None = None,
) -> list[EvalCase]:
    cases: list[EvalCase] = []
    case_counter = 1
    for case_file in sorted(cases_dir.glob("*.json")):
        raw_cases = json.loads(case_file.read_text(encoding="utf-8"))
        for raw in raw_cases:
            expected_val = raw.get("expected")
            if expected_val is None:
                exp_out = raw.get("expected_output")
                expected_val = {"target_agent": exp_out} if exp_out is not None else {}
            elif isinstance(expected_val, str):
                expected_val = {"target_agent": expected_val}

            cases.append(
                EvalCase(
                    id=raw["id"],
                    input=raw["input"],
                    expected=expected_val,
                    tags=raw.get("tags", []),
                    index=raw.get("index") or case_counter,
                )
            )
            case_counter += 1

    # 1. Nếu bật cờ --failed: đọc file result latest của agent để lọc ra danh sách test case FAIL
    if only_failed and agent_name:
        base_results = results_dir or (_find_project_root(cases_dir) / "data" / "eval_results")
        latest_file = base_results / "latest" / f"{agent_name}_latest.json"
        if not latest_file.exists():
            msg = f"⚠️  Không tìm thấy lịch sử chạy gần nhất tại: {latest_file}. Sẽ chạy lại toàn bộ test cases."
            try:
                from rich.console import Console

                Console().print(f"[bold yellow]{msg}[/bold yellow]")
            except ImportError:
                print(msg)
        else:
            try:
                report_data = json.loads(latest_file.read_text(encoding="utf-8"))
                failed_ids = {
                    c["case_id"]
                    for c in report_data.get("cases", [])
                    if not c.get("passed", True)
                }
                if not failed_ids:
                    msg = f"🎉 Tất cả test cases trong lần chạy trước của '{agent_name}' đều đã PASS! Không có case lỗi nào."
                    try:
                        from rich.console import Console

                        Console().print(f"[bold green]{msg}[/bold green]")
                    except ImportError:
                        print(msg)
                    return []

                cases = [c for c in cases if c.id in failed_ids]
                msg = f"🔄 Phát hiện {len(cases)} test cases bị FAIL từ lần chạy trước ({', '.join([c.id for c in cases[:3]])}{'...' if len(cases) > 3 else ''})"
                try:
                    from rich.console import Console

                    Console().print(f"[bold magenta]{msg}[/bold magenta]")
                except ImportError:
                    print(msg)
            except Exception as ex:
                print(f"⚠️ Không thể đọc file latest report: {ex}")

    # 2. Nếu có truyền target_index / ID cụ thể
    if target_index is not None:
        target_str = str(target_index).strip().lower()

        # Tier 1: Khớp exact index số (ví dụ: "2" -> test case thứ 2 trong danh sách)
        if target_str.isdigit():
            idx_num = int(target_str)
            exact_index_cases = [c for c in cases if c.index == idx_num]
            if exact_index_cases:
                return exact_index_cases

            # Tier 1b: Khớp hậu tố số của ID (ví dụ: "2" -> khớp proc_case_002 / sup_demo_002)
            suffix_3 = f"_{idx_num:03d}"
            suffix_2 = f"_{idx_num:02d}"
            suffix_1 = f"_{idx_num}"
            suffix_cases = [
                c
                for c in cases
                if c.id.lower().endswith(suffix_3)
                or c.id.lower().endswith(suffix_2)
                or c.id.lower().endswith(suffix_1)
            ]
            if suffix_cases:
                return suffix_cases

        # Tier 2: Khớp exact ID (ví dụ: "proc_case_002")
        exact_id_cases = [c for c in cases if c.id.lower() == target_str]
        if exact_id_cases:
            return exact_id_cases

        # Tier 3: Khớp exact tag (ví dụ: "request_doc_detail" hoặc "faq")
        tag_cases = [c for c in cases if any(target_str == t.lower() for t in c.tags)]
        if tag_cases:
            return tag_cases

        # Tier 4: Substring match trong case ID (chỉ áp dụng khi KHÔNG phải số thuần túy)
        if not target_str.isdigit():
            substring_cases = [c for c in cases if target_str in c.id.lower()]
            if substring_cases:
                return substring_cases

        try:
            from rich.console import Console

            Console().print(
                f"[bold yellow]⚠️  Không tìm thấy test case nào khớp với index/ID: '{target_index}'[/bold yellow]"
            )
        except ImportError:
            print(f"⚠️  Không tìm thấy test case nào khớp với index/ID: '{target_index}'")
        return []

    return cases


async def run_eval(
    agent_name: str,
    agent_eval_dir: Path,
    agent_fn: AgentFn,
    case_index: str | int | None = None,
    only_failed: bool = False,
) -> EvalReport:
    """agent_fn: hàm async nhận state input (vd {"user_query": ...}) và trả
    về dict output của agent (vd RouteDecision.model_dump() hoặc
    {"final_answer": ...}). Đây chính là entrypoint graph đã compile của
    agent, không phải mock.
    """
    start_total_time = time.perf_counter()
    metrics = _load_metrics(agent_eval_dir / "config.yaml")
    cases = _load_cases(
        agent_eval_dir / "cases",
        target_index=case_index,
        only_failed=only_failed,
        agent_name=agent_name,
    )
    scorer = Scorer(metrics)

    # Thử import rich để hiển thị progress bar đẹp, fallback nếu không có
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
        )
        from rich.text import Text

        console = Console()
        console.print()
        header = Text(f"⚡ Evaluating Agent: {agent_name}", style="bold cyan")
        console.print(Panel(header, border_style="cyan", padding=(0, 2)))

        case_results: list[CaseResult] = []
        total_cases = len(cases)
        if total_cases == 0:
            console.print("[yellow]Không có test case nào để chạy.[/yellow]")
            return EvalReport(agent_name=agent_name, case_results=[])

        with Progress(
            SpinnerColumn(style="green"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(
                bar_width=30,
                style="cyan",
                complete_style="green",
                finished_style="bold green",
            ),
            TextColumn("[bold yellow][{task.completed}/{task.total}][/bold yellow]"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Running {total_cases} test cases...", total=total_cases
            )

            for i, case in enumerate(cases, 1):
                progress.update(
                    task, description=f"[bold blue]⏳ [{i}/{total_cases}] {case.id}"
                )
                start = time.perf_counter()
                try:
                    case_input = dict(case.input)
                    case_input["_eval_case_id"] = case.id
                    case_input["_eval_case_index"] = i
                    actual = await agent_fn(case_input)
                except Exception as ex:
                    latency = time.perf_counter() - start
                    from app.ai.eval.metrics import MetricResult

                    error_result = CaseResult(
                        case_id=case.id,
                        metric_results=[
                            MetricResult(
                                metric_name="agent_error",
                                score=0.0,
                                passed=False,
                                detail=f"{type(ex).__name__}: {str(ex)[:120]}",
                            )
                        ],
                    )
                    case_results.append(error_result)
                    console.print(
                        f"  [bold yellow][{i:02d}/{total_cases}][/bold yellow] [bold red]💥 ERROR[/] [cyan]{case.id}[/cyan] [red]{type(ex).__name__}: {str(ex)[:60]}[/red] [dim]({latency:.2f}s)[/dim]"
                    )
                    progress.advance(task)
                    continue

                latency = time.perf_counter() - start
                result = await scorer.score_case(case, actual, latency_seconds=latency)
                case_results.append(result)

                status_badge = (
                    "[bold green]✓ PASS[/]" if result.passed else "[bold red]✗ FAIL[/]"
                )
                conf_str = ""
                extra_detail = ""

                for m in result.metric_results:
                    if "confidence" in m.metric_name or "min_value" in m.metric_name:
                        conf_str = f" [bold cyan](conf: {m.score:.2f})[/]"
                    elif not m.passed and m.detail:
                        extra_detail = f" [dim red]→ {m.detail[:65]}[/]"

                console.print(
                    f"  [bold yellow][{i:02d}/{total_cases}][/bold yellow] {status_badge} [cyan]{case.id}[/cyan]{conf_str}{extra_detail} [dim]({latency:.2f}s)[/dim]"
                )
                progress.advance(task)

            progress.update(
                task, description=f"[bold green]✅ Completed all {total_cases} cases"
            )

    except ImportError:
        # Fallback nếu rich chưa cài — vẫn chạy bình thường không có giao diện đẹp
        case_results = []
        for i, case in enumerate(cases, 1):
            start = time.perf_counter()
            try:
                case_input = dict(case.input)
                case_input["_eval_case_id"] = case.id
                case_input["_eval_case_index"] = i
                actual = await agent_fn(case_input)
            except Exception as ex:
                latency = time.perf_counter() - start
                from app.ai.eval.metrics import MetricResult

                error_result = CaseResult(
                    case_id=case.id,
                    metric_results=[
                        MetricResult(
                            metric_name="agent_error",
                            score=0.0,
                            passed=False,
                            detail=f"{type(ex).__name__}: {str(ex)[:120]}",
                        )
                    ],
                )
                case_results.append(error_result)
                print(
                    f"  [{i:02d}/{len(cases)}] 💥 ERROR {case.id} ({latency:.2f}s): {type(ex).__name__}"
                )
                continue

            latency = time.perf_counter() - start
            result = await scorer.score_case(case, actual, latency_seconds=latency)
            case_results.append(result)

            status = "✓ PASS" if result.passed else "✗ FAIL"
            conf_str = ""
            for m in result.metric_results:
                if "confidence" in m.metric_name or "min_value" in m.metric_name:
                    conf_str = f" (conf: {m.score:.2f})"
            print(
                f"  [{i:02d}/{len(cases)}] {status} {case.id}{conf_str} ({latency:.2f}s)"
            )

    total_duration = time.perf_counter() - start_total_time
    return EvalReport(
        agent_name=agent_name,
        case_results=case_results,
        execution_time_seconds=total_duration,
    )
