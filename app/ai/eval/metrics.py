"""Các tiêu chí đánh giá (metrics) dùng chung cho mọi agent.

Nguyên tắc tách module này ra khỏi app/ai/agent/<agent>/eval/:
- Logic chấm điểm (làm sao biết đúng/sai, ngưỡng bao nhiêu là đạt) là code
  dùng chung -> sửa 1 chỗ, mọi agent dùng lại, không bị lệch version.
- Agent chỉ khai báo "dùng metric nào, threshold bao nhiêu" qua eval/config.yaml,
  còn *cách tính* nằm ở đây.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class MetricResult:
    metric_name: str
    score: float  # chuẩn hoá về [0.0, 1.0]
    passed: bool
    detail: str = ""


class Metric(abc.ABC):
    """Mọi metric mới (thêm cho agent mới, hoặc dùng chung) implement class này."""

    name: str

    @abc.abstractmethod
    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        """
        expected: field 'expected' của 1 test case.
        actual: output thật của agent khi chạy case đó.
        context: dữ liệu phụ (vd latency_seconds) do runner truyền vào.
        """
        raise NotImplementedError


class ExactFieldMatchMetric(Metric):
    """Đúng/sai tuyệt đối trên 1 field cụ thể của output.

    Dùng cho các quyết định rời rạc — điển hình nhất là routing của
    supervisor: expected={"target_agent": "faq"} vs actual={"target_agent": "faq"}.
    """

    def __init__(self, field: str, name: str | None = None) -> None:
        self.field = field
        self.name = name or f"exact_match:{field}"

    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        exp_val = expected.get(self.field)
        act_val = actual.get(self.field)
        passed = exp_val == act_val
        return MetricResult(
            metric_name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            detail=f"expected={exp_val!r} actual={act_val!r}",
        )


class MinValueMetric(Metric):
    """Kiểm tra 1 field số (vd confidence) >= ngưỡng tối thiểu."""

    def __init__(self, field: str, min_value: float, name: str | None = None) -> None:
        self.field = field
        self.min_value = min_value
        self.name = name or f"min_value:{field}>={min_value}"

    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        act_val = actual.get(self.field)
        passed = isinstance(act_val, (int, float)) and act_val >= self.min_value
        val_score = float(act_val) if isinstance(act_val, (int, float)) else 0.0
        return MetricResult(
            metric_name=self.name,
            score=val_score,
            passed=passed,
            detail=f"confidence={val_score:.2f} (min={self.min_value})",
        )


class LatencyMetric(Metric):
    """Kiểm tra thời gian chạy (giây) không vượt ngưỡng. Runner truyền
    latency_seconds vào context, không lấy từ actual output.
    """

    def __init__(self, max_seconds: float, name: str = "latency") -> None:
        self.max_seconds = max_seconds
        self.name = name

    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        latency = context.get("latency_seconds")
        passed = latency is not None and latency <= self.max_seconds
        return MetricResult(
            metric_name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            detail=f"latency={latency}s (threshold={self.max_seconds}s)",
        )


class LLMJudgeMetric(Metric):
    """Chấm điểm chất lượng câu trả lời tự do (relevance/faithfulness) bằng
    LLM-as-judge. Dùng cho agent trả lời văn bản dài (faq, agentic_rag).
    Mặc định sử dụng AI_PROVIDER từ settings làm Judge.
    """

    def __init__(
        self,
        criterion: str,
        min_score: float = 0.7,
        name: str | None = None,
        judge_provider: str | None = None,
        judge_model: str | None = None,
    ) -> None:
        self.criterion = criterion  # vd: "faithfulness", "relevance"
        self.min_score = min_score
        self.name = name or f"llm_judge:{criterion}"
        self.judge_provider = judge_provider  # None = dùng settings.AI_PROVIDER
        self.judge_model = judge_model

    async def evaluate_async(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        from pydantic import BaseModel, Field

        from app.llmops.factory import get_chat_model

        class JudgeSchema(BaseModel):
            score: float = Field(description="Điểm đánh giá từ 0.0 đến 1.0")
            reason: str = Field(description="Giải thích chi tiết lý do chấm điểm")

        kwargs = {}
        if self.judge_model:
            kwargs["model"] = self.judge_model

        # Dùng provider từ config (hoặc settings.AI_PROVIDER mặc định) làm Judge
        llm = get_chat_model(provider=self.judge_provider, **kwargs)
        structured_llm = llm.with_structured_output(JudgeSchema)

        answer = actual.get("final_answer", "")
        reference = expected.get("reference_answer", "")
        query = context.get("user_query", "")

        judge_prompt = (
            f"Tiêu chí đánh giá: {self.criterion}.\n"
            f"Câu hỏi của người dùng: {query}\n"
            f"Câu trả lời tham chiếu (đúng): {reference}\n"
            f"Câu trả lời cần chấm của chatbot: {answer}\n\n"
            "Hãy chấm điểm mức độ đáp ứng từ 0.0 đến 1.0 và đưa ra lý do ngắn gọn."
        )

        try:
            res = await structured_llm.ainvoke(
                [
                    (
                        "system",
                        "Bạn là giám khảo chuyên nghiệp đánh giá chất lượng câu trả lời của chatbot AI.",
                    ),
                    ("user", judge_prompt),
                ]
            )
            score = float(getattr(res, "score", 0.0))
            detail = getattr(res, "reason", "")
        except Exception as ex:
            score = 0.0
            detail = f"Lỗi gọi LLM Judge ({self.judge_provider}): {ex}"

        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= self.min_score,
            detail=detail,
        )

    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        raise NotImplementedError(
            "LLMJudgeMetric là async — runner phải gọi evaluate_async cho metric này."
        )


class ToolCallMatchMetric(Metric):
    """Đánh giá sự trùng khớp của các tool calls được Agent gọi so với kỳ vọng.
    Kiểm tra danh sách expected_tools (tên công cụ) trong actual.get('tool_calls').
    """

    def __init__(self, name: str = "tool_call_match") -> None:
        self.name = name

    def evaluate(
        self, expected: dict[str, Any], actual: dict[str, Any], **context: Any
    ) -> MetricResult:
        expected_tools = expected.get("expected_tools") or expected.get("expected_tool_calls") or []
        actual_tools = actual.get("tool_calls") or []

        def _extract_name(t: Any) -> str:
            if isinstance(t, str):
                return t
            if isinstance(t, dict):
                return t.get("name") or t.get("tool") or str(t)
            return getattr(t, "name", str(t))

        exp_names = [_extract_name(t) for t in expected_tools]
        act_names = [_extract_name(t) for t in actual_tools]

        if not exp_names and not act_names:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                detail="Không có tool call nào (khớp kỳ vọng)",
            )

        if not exp_names and act_names:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                detail=f"Kỳ vọng không gọi tool nhưng actual gọi: {act_names}",
            )

        if exp_names and not act_names:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                detail=f"Kỳ vọng gọi {exp_names} nhưng actual không gọi tool nào",
            )

        matched = [name for name in exp_names if name in act_names]
        score = len(matched) / len(exp_names) if exp_names else 1.0
        passed = score >= 1.0

        detail = f"expected={exp_names} actual={act_names} matched={matched}"
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=passed,
            detail=detail,
        )
