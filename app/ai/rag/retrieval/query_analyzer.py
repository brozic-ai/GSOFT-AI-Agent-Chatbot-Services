"""
Query Analyzer — Bộ phân tích đặc tính và ý định câu hỏi để xác định Dynamic Top-K cho RAG.

Nhiệm vụ:
- Phân tích câu hỏi tiếng Việt không dùng LLM (Zero-LLM Latency, < 1ms)
- Phân loại câu hỏi thành:
  + EXHAUSTIVE / LIST (Liệt kê, bao quát, danh sách, toàn bộ) -> Top-K lớn (10 - 15)
  + SPECIFIC / FOCUSED (Hỏi đích danh 1 người, 1 con số, 1 nút bấm, 1 định nghĩa) -> Top-K nhỏ (3 - 5)
  + STANDARD (Truy vấn nghiệp vụ thông thường) -> Top-K tiêu chuẩn (5 - 6)
- Đảm bảo giá trị Top-K luôn nằm trong khoảng cấu hình [MIN_TOP_K, MAX_TOP_K].
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueryCategory(str, Enum):
    SPECIFIC = "specific"
    EXHAUSTIVE = "exhaustive"
    STANDARD = "standard"


@dataclass
class QueryAnalysisResult:
    """Kết quả phân tích đặc tính câu hỏi."""

    category: QueryCategory
    recommended_top_k: int
    is_exhaustive: bool
    is_specific: bool
    matched_patterns: list[str] = field(default_factory=list)
    reasoning: str = ""


class QueryAnalyzer:
    """Bộ phân tích đặc tính câu hỏi và tính toán Dynamic Top-K."""

    # Nhóm 1: Các mẫu câu hỏi mang tính LIỆT KÊ, TOÀN BỘ, DANH SÁCH (Exhaustive/List)
    _EXHAUSTIVE_PATTERNS = [
        # Liệt kê / Toàn bộ / Tất cả
        (r"\b(tất cả|toàn bộ|tất thảy|hết|mọi|toàn thể)\b", "toàn bộ / tất cả"),
        (r"\b(liệt kê|danh sách|danh mục|bảng kê|thống kê)\b", "liệt kê / danh sách"),
        # Cấu trúc thành phần & số lượng
        (r"\b(có những gì|gồm những gì|bao gồm những gì|bao gồm các|gồm các|gồm những|có các|có những)\b", "gồm những gì / bao gồm"),
        (r"\b(các bước|những bước|quy trình gồm|trình tự gồm|các giai đoạn|từng bước)\b", "các bước / quy trình"),
        # Phân loại / Tập hợp
        (r"\b(các loại|những loại|phân loại|những dạng|các dạng)\b", "các loại / phân loại"),
        (r"\b(các trường hợp|những trường hợp|trường hợp nào|các tình huống)\b", "các trường hợp"),
        (r"\b(những ai|các bên|các vai trò|những vai trò|các phòng ban|những phòng ban|các bộ phận)\b", "các vai trò / phòng ban"),
        # Tổng hợp / So sánh
        (r"\b(tổng hợp|tổng quan|so sánh|khác nhau thế nào|khác biệt giữa|phân biệt giữa)\b", "tổng hợp / so sánh"),
        # Hồ sơ / Điều kiện
        (r"\b(hồ sơ gồm|chứng từ gồm|thủ tục gồm|điều kiện gì|những điều kiện|các điều kiện|tiêu chuẩn gồm)\b", "hồ sơ / điều kiện"),
        # Chi tiết
        (r"\b(chi tiết các|nội dung các|quy định về các)\b", "chi tiết các"),
    ]

    # Nhóm 2: Các mẫu câu hỏi mang tính CỤ THỂ, ĐÍCH DANH (Specific/Focused)
    _SPECIFIC_PATTERNS = [
        # Hỏi đích danh vai trò / người duyệt
        (r"\b(ai là người|ai duyệt|ai phê duyệt|người duyệt là ai|ai chịu trách nhiệm|ai có quyền|ai ký)\b", "người duyệt / đích danh"),
        # Hỏi con số / hạn mức / tiền / thời hạn cụ thể
        (r"\b(hạn mức bao nhiêu|bao nhiêu tiền|số tiền bao nhiêu|tối đa bao nhiêu|tối thiểu bao nhiêu)\b", "hạn mức / số tiền"),
        (r"\b(bao nhiêu ngày|mấy ngày|thời hạn bao lâu|thời gian bao lâu|khi nào xong)\b", "thời hạn / số ngày"),
        # Hỏi vị trí / màn hình / nút bấm
        (r"\b(ở đâu|chỗ nào|màn hình nào|vào đâu|vị trí nào|link nào|menu nào|nút nào|tab nào)\b", "vị trí / màn hình"),
        # Hỏi mã số / thông tin định danh
        (r"\b(mã số mấy|mã là gì|hotline|số điện thoại|email nào|địa chỉ nào)\b", "mã số / liên hệ"),
        # Hỏi định nghĩa / ý nghĩa khái niệm đơn lẻ
        (r"\b(là gì|nghĩa là gì|được hiểu là gì|định nghĩa)\b", "định nghĩa khái niệm"),
    ]

    def __init__(
        self,
        min_top_k: int | None = None,
        max_top_k: int | None = None,
        default_top_k: int | None = None,
        specific_top_k: int | None = None,
        exhaustive_top_k: int | None = None,
        enabled: bool | None = None,
    ):
        self.enabled = (
            enabled
            if enabled is not None
            else getattr(settings, "RAG_DYNAMIC_TOP_K_ENABLED", True)
        )
        self.min_top_k = (
            min_top_k
            if min_top_k is not None
            else getattr(settings, "RAG_MIN_TOP_K", 3)
        )
        self.max_top_k = (
            max_top_k
            if max_top_k is not None
            else getattr(settings, "RAG_MAX_TOP_K", 15)
        )
        self.default_top_k = (
            default_top_k
            if default_top_k is not None
            else getattr(settings, "RAG_DEFAULT_TOP_K", 5)
        )
        self.specific_top_k = (
            specific_top_k
            if specific_top_k is not None
            else getattr(settings, "RAG_SPECIFIC_TOP_K", 3)
        )
        self.exhaustive_top_k = (
            exhaustive_top_k
            if exhaustive_top_k is not None
            else getattr(settings, "RAG_EXHAUSTIVE_TOP_K", 12)
        )

    def analyze(self, query: str) -> QueryAnalysisResult:
        """
        Phân tích câu hỏi và trả về kết quả phân loại kèm Top-K kiến nghị.
        """
        if not self.enabled:
            return QueryAnalysisResult(
                category=QueryCategory.STANDARD,
                recommended_top_k=self.default_top_k,
                is_exhaustive=False,
                is_specific=False,
                matched_patterns=[],
                reasoning="Dynamic Top-K bị tắt, sử dụng default_top_k.",
            )

        q_clean = query.strip().lower()
        if not q_clean:
            return QueryAnalysisResult(
                category=QueryCategory.STANDARD,
                recommended_top_k=self.default_top_k,
                is_exhaustive=False,
                is_specific=False,
                matched_patterns=[],
                reasoning="Câu hỏi rỗng, dùng default_top_k.",
            )

        matched_exhaustive = []
        for pattern, label in self._EXHAUSTIVE_PATTERNS:
            if re.search(pattern, q_clean, re.IGNORECASE):
                matched_exhaustive.append(label)

        matched_specific = []
        for pattern, label in self._SPECIFIC_PATTERNS:
            if re.search(pattern, q_clean, re.IGNORECASE):
                matched_specific.append(label)

        # Quyết định phân loại:
        # Nếu có từ khóa exhaustive -> Ưu tiên Exhaustive (để không bị sót thông tin)
        if matched_exhaustive:
            # Nếu có nhiều pattern liệt kê hoặc câu hỏi dài -> nâng lên max_top_k (ví dụ 12-15)
            k = max(self.exhaustive_top_k, min(self.max_top_k, 10 + len(matched_exhaustive) * 2))
            k = max(self.min_top_k, min(self.max_top_k, k))
            reasoning = f"Phát hiện ý định liệt kê/bao quát ({', '.join(matched_exhaustive)}) -> Top-K: {k}"
            logger.info("[DYNAMIC TOP-K] Query='%s' -> EXHAUSTIVE (Top-K: %d)", query[:60], k)
            return QueryAnalysisResult(
                category=QueryCategory.EXHAUSTIVE,
                recommended_top_k=k,
                is_exhaustive=True,
                is_specific=False,
                matched_patterns=matched_exhaustive,
                reasoning=reasoning,
            )

        # Nếu có từ khóa specific và không có từ khóa exhaustive -> Specific
        if matched_specific:
            k = max(self.min_top_k, min(self.default_top_k, self.specific_top_k))
            reasoning = f"Phát hiện ý định hỏi đích danh/cụ thể ({', '.join(matched_specific)}) -> Top-K: {k}"
            logger.info("[DYNAMIC TOP-K] Query='%s' -> SPECIFIC (Top-K: %d)", query[:60], k)
            return QueryAnalysisResult(
                category=QueryCategory.SPECIFIC,
                recommended_top_k=k,
                is_exhaustive=False,
                is_specific=True,
                matched_patterns=matched_specific,
                reasoning=reasoning,
            )

        # Các câu hỏi ngắn dưới 8 từ không chứa từ khóa mở rộng -> thiên hướng specific nhẹ
        word_count = len(q_clean.split())
        if word_count <= 6 and ("nào" in q_clean or "gì" in q_clean or "ai" in q_clean):
            k = max(self.min_top_k, min(self.default_top_k, 4))
            return QueryAnalysisResult(
                category=QueryCategory.SPECIFIC,
                recommended_top_k=k,
                is_exhaustive=False,
                is_specific=True,
                matched_patterns=["câu hỏi ngắn"],
                reasoning=f"Câu hỏi ngắn ({word_count} từ) tập trung đối tượng cụ thể -> Top-K: {k}",
            )

        # Mặc định: STANDARD
        k = max(self.min_top_k, min(self.max_top_k, self.default_top_k))
        return QueryAnalysisResult(
            category=QueryCategory.STANDARD,
            recommended_top_k=k,
            is_exhaustive=False,
            is_specific=False,
            matched_patterns=[],
            reasoning=f"Câu hỏi nghiệp vụ chuẩn -> Top-K: {k}",
        )


_default_analyzer = None


def get_query_analyzer() -> QueryAnalyzer:
    """Singleton getter cho QueryAnalyzer."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = QueryAnalyzer()
    return _default_analyzer


def determine_dynamic_top_k(query: str, requested_top_k: int | None = None) -> tuple[int, QueryAnalysisResult]:
    """
    Hàm tiện ích tính toán Dynamic Top-K cho query.
    Nếu requested_top_k được truyền và khác giá trị mặc định 5, ưu tiên requested_top_k nhưng vẫn clamp [MIN, MAX].
    """
    analyzer = get_query_analyzer()
    analysis = analyzer.analyze(query)

    # Nếu caller truyền requested_top_k rõ ràng (khác None và khác default 5), tôn trọng caller
    if requested_top_k is not None and requested_top_k != getattr(settings, "RAG_DEFAULT_TOP_K", 5):
        clamped_k = max(analyzer.min_top_k, min(analyzer.max_top_k, requested_top_k))
        return clamped_k, analysis

    return analysis.recommended_top_k, analysis
