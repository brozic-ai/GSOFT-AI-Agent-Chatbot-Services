"""Định nghĩa 1 test case và cách gộp nhiều MetricResult thành kết quả 1 case."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.eval.metrics import Metric, MetricResult


@dataclass
class EvalCase:
    id: str
    input: dict[str, Any]  # payload truyền vào agent, vd {"user_query": "..."}
    expected: dict[str, Any]  # giá trị kỳ vọng, khớp field với metric tương ứng
    tags: list[str] = field(default_factory=list)
    index: int | None = None


@dataclass
class CaseResult:
    case_id: str
    metric_results: list[MetricResult]
    expected: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    case_input: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metric_results)

    @property
    def avg_score(self) -> float:
        if not self.metric_results:
            return 0.0
        return sum(m.score for m in self.metric_results) / len(self.metric_results)


class Scorer:
    """Chạy 1 danh sách Metric lên 1 case, hỗ trợ cả metric sync và async
    (LLMJudgeMetric.evaluate_async) trong cùng 1 danh sách.
    """

    def __init__(self, metrics: list[Metric]) -> None:
        self.metrics = metrics

    async def score_case(
        self,
        case: EvalCase,
        actual: dict[str, Any],
        latency_seconds: float | None = None,
    ) -> CaseResult:
        results: list[MetricResult] = []
        context = {"latency_seconds": latency_seconds, **case.input}

        for metric in self.metrics:
            evaluate_async = getattr(metric, "evaluate_async", None)
            if evaluate_async is not None:
                result = await evaluate_async(case.expected, actual, **context)
            else:
                result = metric.evaluate(case.expected, actual, **context)
            results.append(result)

        return CaseResult(
            case_id=case.id,
            metric_results=results,
            expected=case.expected,
            actual=actual,
            case_input=case.input,
        )
