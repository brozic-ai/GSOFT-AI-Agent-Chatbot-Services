"""In kết quả EvalReport ra console (Rich UI) và/hoặc ghi ra file JSON
để lưu lịch sử (so sánh giữa các lần chạy, các version prompt).

Bổ sung các tính năng Enterprise LLMOps:
1. Classification Metrics (Accuracy, Precision, Recall, F1-Score cho từng nhóm Intent)
2. Confidence Score Calibration (Độ tin cậy điểm Confidence vs Thực tế)
3. Error Analysis & Confusion Matrix (Ma trận nhầm lẫn 2D + Log Misclassified Cases kèm LLM Reasoning)
4. Benchmark Threshold Check (Ngưỡng benchmark tối thiểu, vd 90% Pass Rate để duyệt Prompt)
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from app.ai.eval.runner import EvalReport
from app.ai.eval.scorer import CaseResult


def _score_color(score: float) -> str:
    """Trả về style màu dựa trên giá trị score."""
    if score >= 0.9:
        return "bold green"
    elif score >= 0.7:
        return "yellow"
    elif score >= 0.5:
        return "dark_orange"
    return "bold red"


def _pass_rate_bar(rate: float, width: int = 20) -> str:
    """Tạo thanh tiến trình ASCII cho pass rate."""
    filled = int(rate * width)
    empty = width - filled
    if rate >= 0.9:
        color = "green"
    elif rate >= 0.7:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}] {rate:.0%}"


def compute_classification_metrics(case_results: list[CaseResult]) -> dict[str, Any]:
    """Tính toán tự động các chỉ số Phân loại (Classification Metrics):
    - Accuracy, Precision, Recall, F1-Score cho từng nhóm intent (faq, rag, gamspro, fallback)
    - Confusion Matrix 2D
    - Đánh giá độ tin cậy của Confidence Score (Confidence Calibration).
    """
    all_intents: set[str] = set()
    y_true: list[str] = []
    y_pred: list[str] = []
    confidences: list[float] = []

    for c in case_results:
        exp_intent = str(
            c.expected.get("target_agent") or c.expected.get("intent") or "unknown"
        ).lower()
        act_intent = str(
            c.actual.get("target_agent") or c.actual.get("intent") or "unknown"
        ).lower()

        y_true.append(exp_intent)
        y_pred.append(act_intent)
        all_intents.add(exp_intent)
        all_intents.add(act_intent)

        conf = float(c.actual.get("confidence", 1.0))
        confidences.append(conf)

    if not y_true:
        return {}

    intent_list = sorted(list(all_intents))

    # 1. Tính toán Confusion Matrix (2D Dict)
    confusion_matrix: dict[str, dict[str, int]] = {
        exp: {act: 0 for act in intent_list} for exp in intent_list
    }
    for t, p in zip(y_true, y_pred):
        if t in confusion_matrix and p in confusion_matrix[t]:
            confusion_matrix[t][p] += 1

    # 2. Tính toán Per-Class Metrics (Precision, Recall, F1)
    per_class: dict[str, dict[str, Any]] = {}
    total_samples = len(y_true)
    total_correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    overall_accuracy = total_correct / total_samples if total_samples > 0 else 0.0

    for intent in intent_list:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == intent and p == intent)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != intent and p == intent)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == intent and p != intent)
        support = sum(1 for t in y_true if t == intent)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        per_class[intent] = {
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        }

    macro_precision = (
        sum(v["precision"] for v in per_class.values()) / len(intent_list)
        if intent_list
        else 0.0
    )
    macro_recall = (
        sum(v["recall"] for v in per_class.values()) / len(intent_list)
        if intent_list
        else 0.0
    )
    macro_f1 = (
        sum(v["f1_score"] for v in per_class.values()) / len(intent_list)
        if intent_list
        else 0.0
    )

    # 3. Đánh giá độ tin cậy của Confidence Score (Confidence Calibration)
    correct_confs = [conf for t, p, conf in zip(y_true, y_pred, confidences) if t == p]
    incorrect_confs = [
        conf for t, p, conf in zip(y_true, y_pred, confidences) if t != p
    ]

    avg_conf_all = sum(confidences) / len(confidences) if confidences else 0.0
    avg_conf_correct = (
        sum(correct_confs) / len(correct_confs) if correct_confs else 0.0
    )
    avg_conf_incorrect = (
        sum(incorrect_confs) / len(incorrect_confs) if incorrect_confs else 0.0
    )

    calibration_gap = abs(avg_conf_all - overall_accuracy)

    if calibration_gap <= 0.05:
        verdict = "Perfect / Well Calibrated"
    elif avg_conf_all > overall_accuracy:
        verdict = "Overconfident (LLM tự tin quá mức khi đoán sai)"
    else:
        verdict = "Underconfident (LLM quá thận trọng)"

    calibration_metrics = {
        "overall_accuracy": round(overall_accuracy, 4),
        "mean_confidence": round(avg_conf_all, 4),
        "mean_confidence_correct": round(avg_conf_correct, 4),
        "mean_confidence_incorrect": round(avg_conf_incorrect, 4),
        "calibration_gap": round(calibration_gap, 4),
        "calibration_verdict": verdict,
    }

    return {
        "overall_accuracy": round(overall_accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "intent_list": intent_list,
        "confusion_matrix": confusion_matrix,
        "per_class": per_class,
        "confidence_calibration": calibration_metrics,
    }


def print_report(
    report: EvalReport, min_pass_rate_threshold: float = 0.90
) -> bool:
    """In báo cáo eval với Rich UI đẹp:
    - Panel Header & Pass Rate Bar
    - Results Table
    - Classification Metrics Table (Accuracy, Precision, Recall, F1)
    - Confusion Matrix Grid (Ma trận nhầm lẫn 2D)
    - Confidence Calibration Panel
    - Detailed Misclassified Cases (với User Query & LLM Reasoning)
    - Benchmark Threshold Alert Panel
    """
    benchmark_passed = report.pass_rate >= min_pass_rate_threshold

    try:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()
        console.print()

        # ── Header Panel ──
        passed_count = sum(1 for c in report.case_results if c.passed)
        total_count = len(report.case_results)
        rate = report.pass_rate

        if rate >= min_pass_rate_threshold:
            header_style = "bold green"
            border_style = "green"
            emoji = "🏆"
        elif rate >= 0.7:
            header_style = "bold yellow"
            border_style = "yellow"
            emoji = "⚠️"
        else:
            header_style = "bold red"
            border_style = "red"
            emoji = "❌"

        header_text = Text()
        header_text.append(f"{emoji} Agent: ", style="bold white")
        header_text.append(f"{report.agent_name}", style="bold cyan")
        header_text.append("  │  ", style="dim")
        header_text.append(f"Pass: {passed_count}/{total_count}", style=header_style)
        header_text.append("  │  ", style="dim")
        header_text.append(
            f"Avg Score: {report.avg_score:.2f}", style=_score_color(report.avg_score)
        )

        console.print(Panel(header_text, border_style=border_style, padding=(0, 1)))

        # ── Pass Rate Bar ──
        bar_text = Text()
        bar_text.append("  Pass Rate: ", style="bold white")
        console.print(bar_text, end="")
        console.print(_pass_rate_bar(rate))
        console.print()

        # ── Results Table ──
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            border_style="bright_black",
            row_styles=["", "dim"],
            title_justify="left",
            pad_edge=True,
        )
        table.add_column("Status", justify="center", width=8, no_wrap=True)
        table.add_column("Test Case", style="cyan", min_width=25)
        table.add_column("Score", justify="center", width=8)
        table.add_column("Metrics", ratio=1)

        for case in report.case_results:
            status = (
                "[bold green]✓ PASS[/]" if case.passed else "[bold red]✗ FAIL[/]"
            )
            score_str = f"[{_score_color(case.avg_score)}]{case.avg_score:.2f}[/]"

            metric_parts = []
            for m in case.metric_results:
                if m.passed:
                    if "confidence" in m.metric_name or "min_value" in m.metric_name:
                        badge = f"[green]● {m.metric_name}[/] [bold cyan](conf: {m.score:.2f})[/]"
                    else:
                        badge = f"[green]● {m.metric_name}[/] [dim]{m.score:.2f}[/]"
                else:
                    badge = f"[red]○ {m.metric_name}[/] [dim]{m.score:.2f}[/]"
                    if m.detail:
                        badge += f" [dim italic]({m.detail[:60]})[/]"
                metric_parts.append(badge)

            metrics_str = "  ".join(metric_parts)
            table.add_row(status, case.case_id, score_str, metrics_str)

        console.print(table)

        class_metrics = compute_classification_metrics(report.case_results)

        # ── Classification Metrics Table ──
        if class_metrics and "per_class" in class_metrics:
            console.print()
            cls_table = Table(
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
                border_style="cyan",
                title="📊 Bảng Chỉ Số Phân Loại Intent (Classification Metrics)",
                title_justify="left",
            )
            cls_table.add_column("Intent Group", style="bold white", width=16)
            cls_table.add_column("Support", justify="center", width=10)
            cls_table.add_column("Precision", justify="center", width=12)
            cls_table.add_column("Recall", justify="center", width=12)
            cls_table.add_column("F1-Score", justify="center", width=12)

            for intent, m in class_metrics["per_class"].items():
                p_str = f"{m['precision']:.2%}"
                r_str = f"{m['recall']:.2%}"
                f1_str = f"[{_score_color(m['f1_score'])}]{m['f1_score']:.2%}[/]"
                cls_table.add_row(intent, str(m["support"]), p_str, r_str, f1_str)

            macro_p = f"{class_metrics['macro_precision']:.2%}"
            macro_r = f"{class_metrics['macro_recall']:.2%}"
            macro_f1 = f"[{_score_color(class_metrics['macro_f1'])}]{class_metrics['macro_f1']:.2%}[/]"
            cls_table.add_row(
                "[bold yellow]Macro Avg[/]",
                str(len(report.case_results)),
                macro_p,
                macro_r,
                macro_f1,
                end_section=True,
            )

            console.print(cls_table)

            # ── 2D Confusion Matrix Grid Table ──
            intents = class_metrics.get("intent_list", [])
            cm = class_metrics.get("confusion_matrix", {})
            if intents and cm:
                console.print()
                cm_table = Table(
                    box=box.ROUNDED,
                    show_header=True,
                    header_style="bold yellow",
                    border_style="yellow",
                    title="🔀 Ma Trận Nhầm Lẫn 2D (Confusion Matrix Grid: Expected ↓ vs Actual →)",
                    title_justify="left",
                )
                cm_table.add_column(
                    "Expected \\ Actual", style="bold white", width=18
                )
                for intent in intents:
                    cm_table.add_column(intent, justify="center", width=12)

                for exp in intents:
                    row_cells = [f"[bold white]{exp}[/]"]
                    for act in intents:
                        count = cm.get(exp, {}).get(act, 0)
                        if exp == act:
                            val_str = (
                                f"[bold green]{count}[/]"
                                if count > 0
                                else "[dim]0[/]"
                            )
                        else:
                            val_str = (
                                f"[bold red]{count}[/]"
                                if count > 0
                                else "[dim]0[/]"
                            )
                        row_cells.append(val_str)
                    cm_table.add_row(*row_cells)

                console.print(cm_table)

            # ── Confidence Calibration Panel ──
            cal = class_metrics.get("confidence_calibration", {})
            cal_lines = [
                f"🎯 [bold white]Accuracy thực tế:[/] [bold green]{cal.get('overall_accuracy', 0):.2%}[/]",
                f"🧠 [bold white]LLM Mean Confidence:[/] [bold cyan]{cal.get('mean_confidence', 0):.2%}[/]",
                f"✅ [bold white]Mean Conf (Case đúng):[/] [green]{cal.get('mean_confidence_correct', 0):.2%}[/]",
                f"❌ [bold white]Mean Conf (Case sai):[/] [red]{cal.get('mean_confidence_incorrect', 0):.2%}[/]",
                f"⚖️ [bold white]Đánh giá độ tin cậy:[/] [bold yellow]{cal.get('calibration_verdict', '')}[/]",
            ]
            console.print(
                Panel(
                    "\n".join(cal_lines),
                    title="[bold magenta]🔍 Đánh Giá Độ Tin Cậy Confidence Score (Confidence Calibration)[/]",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )

        # ── Error Analysis: Misclassified Cases Logging ──
        misclassified = [
            c
            for c in report.case_results
            if not c.passed
            or (
                str(c.expected.get("target_agent") or "").lower()
                != str(c.actual.get("target_agent") or c.actual.get("intent") or "").lower()
            )
        ]
        if misclassified:
            console.print()
            err_lines = []
            for c in misclassified:
                exp_intent = c.expected.get("target_agent") or c.expected.get("intent") or "unknown"
                act_intent = c.actual.get("target_agent") or c.actual.get("intent") or "unknown"
                conf = c.actual.get("confidence", 0.0)
                user_query = c.case_input.get("user_query") or "N/A"
                reasoning = (
                    c.actual.get("reasoning")
                    or c.actual.get("explanation")
                    or "Không có reasoning từ LLM"
                )

                err_lines.append(
                    f"❌ [bold cyan]{c.case_id}[/]\n"
                    f"   💬 [bold white]User Query:[/] \"{user_query}\"\n"
                    f"   🔀 [bold red]Expected:[/] [bold green]{exp_intent}[/] ➔  [bold red]Actual:[/] [bold red]{act_intent}[/] [dim cyan](conf: {conf:.2f})[/]\n"
                    f"   🧠 [bold yellow]LLM Reasoning:[/] [italic]{reasoning}[/]\n"
                )

            err_text = "\n".join(err_lines)
            console.print(
                Panel(
                    err_text,
                    title="[bold red]🚨 Error Analysis: Danh Sách Misclassified Cases & LLM Reasoning[/]",
                    border_style="red",
                    padding=(1, 2),
                )
            )

        # ── Benchmark Threshold Check Alert Panel ──
        console.print()
        if benchmark_passed:
            bench_text = f"✅ [bold green]BENCHMARK PASSED![/] Accuracy ({rate:.1%}) >= Ngưỡng tối thiểu ({min_pass_rate_threshold:.1%}). Đủ điều kiện duyệt Prompt!"
            console.print(Panel(bench_text, border_style="green", padding=(0, 2)))
        else:
            bench_text = f"🚨 [bold red]BENCHMARK FAILED![/] Accuracy ({rate:.1%}) < Ngưỡng tối thiểu ({min_pass_rate_threshold:.1%}). Không đủ điều kiện duyệt Prompt!"
            console.print(Panel(bench_text, border_style="red", padding=(0, 2)))

        console.print()

    except ImportError:
        # Fallback: plain text output nếu rich chưa cài
        print(f"\n=== Eval report: {report.agent_name} ===")
        print(f"Pass rate : {report.pass_rate:.0%}")
        print(f"Avg score : {report.avg_score:.2f}")
        print("-" * 50)

        for case in report.case_results:
            status = "PASS" if case.passed else "FAIL"
            print(f"[{status}] {case.case_id} (avg={case.avg_score:.2f})")

    return benchmark_passed


def save_report_json(
    report: EvalReport,
    base_dir: Path | str = "data/eval_results",
    output_path: Path | None = None,
    min_pass_rate_threshold: float = 0.90,
) -> Path:
    """Lưu kết quả Eval chuẩn Enterprise LLMOps:
    1. history/<agent_name>/YYYY-MM-DD_HH-MM-SS_passXX%.json (Lưu vết lịch sử)
    2. latest/<agent_name>_latest.json (File mới nhất cho CI/CD)
    3. benchmark_summary.json (Báo cáo tổng quan so sánh các Agent)
    """
    from datetime import datetime

    from app.core.config import settings

    now = datetime.now(UTC)
    timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    timestamp_iso = now.isoformat()

    total_cases = len(report.case_results)
    passed_cases = sum(1 for c in report.case_results if c.passed)
    failed_cases = total_cases - passed_cases
    pass_pct = int(report.pass_rate * 100)

    class_metrics = compute_classification_metrics(report.case_results)
    benchmark_passed = report.pass_rate >= min_pass_rate_threshold

    payload = {
        "metadata": {
            "agent_name": report.agent_name,
            "timestamp_utc": timestamp_iso,
            "environment": getattr(settings, "ENVIRONMENT", "local"),
            "llm_provider": getattr(settings, "AI_PROVIDER", "unknown"),
            "llm_model": getattr(settings, "LLM_MODEL", "unknown"),
            "execution_time_seconds": round(report.execution_time_seconds, 2),
            "benchmark_threshold": min_pass_rate_threshold,
            "benchmark_passed": benchmark_passed,
        },
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": round(report.pass_rate, 4),
            "pass_percentage": f"{pass_pct}%",
            "avg_score": round(report.avg_score, 4),
            "accuracy": class_metrics.get("overall_accuracy", round(report.pass_rate, 4)),
            "macro_f1": class_metrics.get("macro_f1", 0.0),
        },
        "classification_metrics": class_metrics.get("per_class", {}),
        "confusion_matrix": class_metrics.get("confusion_matrix", {}),
        "confidence_calibration": class_metrics.get("confidence_calibration", {}),
        "cases": [
            {
                "case_id": c.case_id,
                "passed": c.passed,
                "avg_score": round(c.avg_score, 4),
                "expected": c.expected,
                "actual": c.actual,
                "user_query": c.case_input.get("user_query"),
                "reasoning": c.actual.get("reasoning") or c.actual.get("explanation"),
                "metrics": [
                    {
                        "name": m.metric_name,
                        "score": round(m.score, 4),
                        "passed": m.passed,
                        "detail": m.detail,
                    }
                    for m in c.metric_results
                ],
            }
            for c in report.case_results
        ],
    }

    json_content = json.dumps(payload, ensure_ascii=False, indent=2)
    root_dir = Path(base_dir)

    history_dir = root_dir / "history" / report.agent_name
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = (
        history_dir / f"{timestamp_str}_{report.agent_name}_pass{pass_pct}%.json"
    )
    history_file.write_text(json_content, encoding="utf-8")

    latest_dir = root_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_file = latest_dir / f"{report.agent_name}_latest.json"
    latest_file.write_text(json_content, encoding="utf-8")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_content, encoding="utf-8")

    summary_file = root_dir / "benchmark_summary.json"
    summary_data: dict = {}
    if summary_file.exists():
        try:
            summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            summary_data = {}

    summary_data[report.agent_name] = {
        "agent_name": report.agent_name,
        "last_run_utc": timestamp_iso,
        "pass_percentage": f"{pass_pct}%",
        "pass_rate": round(report.pass_rate, 4),
        "accuracy": class_metrics.get("overall_accuracy", round(report.pass_rate, 4)),
        "macro_f1": class_metrics.get("macro_f1", 0.0),
        "benchmark_passed": benchmark_passed,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "execution_time_seconds": round(report.execution_time_seconds, 2),
        "llm_provider": getattr(settings, "AI_PROVIDER", "unknown"),
        "llm_model": getattr(settings, "LLM_MODEL", "unknown"),
        "latest_report": f"latest/{report.agent_name}_latest.json",
        "history_report": f"history/{report.agent_name}/{history_file.name}",
    }

    summary_file.write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    push_to_langsmith_if_enabled(report, payload)

    try:
        from rich.console import Console

        console = Console()
        console.print(
            f"  📁 [bold green]Report Saved Successfully![/]\n"
            f"     • [bold cyan]Latest  :[/] {latest_file}\n"
            f"     • [dim]History :[/] {history_file}\n"
            f"     • [bold magenta]Summary :[/] {summary_file}",
            style="dim",
        )
    except ImportError:
        print(f"  Report saved to {latest_file} and {history_file}")

    return latest_file


def push_to_langsmith_if_enabled(report: EvalReport, payload: dict[str, Any]) -> None:
    """Tự động đẩy kết quả Evaluation & Feedback metrics lên công cụ LLMOps LangSmith
    nếu biến môi trường LANGCHAIN_TRACING_V2=true và LANGCHAIN_API_KEY được khai báo.
    """
    import os

    if (
        os.getenv("LANGCHAIN_TRACING_V2", "").lower() != "true"
        or not os.getenv("LANGCHAIN_API_KEY")
    ):
        return

    try:
        from langsmith import Client

        client = Client()
        project_name = os.getenv("LANGCHAIN_PROJECT", "bvbank-llm-service-eval")

        summary = payload.get("summary", {})
        client.create_feedback(
            run_id=None,
            key=f"{report.agent_name}_pass_rate",
            score=report.pass_rate,
            comment=f"Pass Rate: {report.pass_rate:.2%}, Accuracy: {summary.get('accuracy', 0):.2%}, Macro F1: {summary.get('macro_f1', 0):.2%}",
        )

        try:
            from rich.console import Console

            Console().print(
                f"  ☁️ [bold cyan]LangSmith LLMOps:[/] Metrics synced to project '{project_name}'"
            )
        except ImportError:
            print(f"  LangSmith LLMOps: Metrics synced to project '{project_name}'")
    except Exception:
        pass
