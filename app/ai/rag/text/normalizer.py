"""
Module chuẩn hóa tiếng Việt cho RAG (Vietnamese Text Preprocessing).

Hỗ trợ:
- Chuẩn hóa Unicode NFC và dấu tiếng Việt (underthesea).
- Xóa ký tự ẩn (zero-width) và lọc nhiễu ký tự rác.
- Khử lặp ký tự kéo dài (Deduplication).
- Mở rộng từ viết tắt chuyên ngành ngân hàng (bank_acronyms.json).
- Chuẩn hóa khoảng trắng và dấu câu hợp lệ.
"""

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)

try:
    from underthesea import text_normalize
except ImportError:
    text_normalize = None


def _load_bank_acronyms() -> list[tuple[re.Pattern[str], str]]:
    """Tải danh sách từ viết tắt ngân hàng từ file bank_acronyms.json."""
    json_path = Path(__file__).parent / "bank_acronyms.json"
    if not json_path.exists():
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data: dict[str, str] = json.load(f)
        # Sắp xếp từ dài hơn lên trước để tránh xung đột tiền tố (ví dụ: HĐTD trước HĐ, TKKH trước TK)
        sorted_items = sorted(data.items(), key=lambda x: len(x[0]), reverse=True)
        return [
            (re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE), full_form)
            for abbr, full_form in sorted_items
        ]
    except Exception as ex:
        logger.warning("Không thể tải bank_acronyms.json: %s", ex)
        return []


class VietnameseNormalizer:
    """Normalizer tối ưu cho tiếng Việt trước khi Vector Embedding và Retrieval."""

    # 1. Ký tự ẩn và khoảng trắng
    _ZERO_WIDTH_PATTERN = re.compile(
        r"[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a-\u202e\x00-\x08\x0b\x0c\x0e-\x1f]"
    )
    _HORIZ_WHITESPACE = re.compile(r"[ \t\f\v]+")
    _MULTIPLE_NEWLINES = re.compile(r"\n{3,}")

    # 2. Lọc nhiễu ký tự đặc biệt
    _JUNK_SYMBOLS_PATTERN = re.compile(r"[!@#$%^&*~+=/\\|<>{}\[\]`_]{2,}")
    _ISOLATED_SYMBOLS_PATTERN = re.compile(r"(?<!\S)[!@#$%^&*~+=/\\|<>{}\[\]`_]+(?!\S)")

    # 3. Khử lặp ký tự và dấu câu
    _ELONGATION_PATTERN = re.compile(r"([a-zA-Zà-ỹÀ-Ỹ])\1{2,}")
    _PUNCT_REPEAT_PATTERN = re.compile(r"([.?!,;:])\1+")
    _LEADING_PUNCT_PATTERN = re.compile(r"^\s*[,.;:!?/\\_-]+\s*")

    # 4. Chuẩn hóa khoảng cách quanh dấu câu
    _PUNCT_ATTACH_BEFORE = re.compile(r"([a-zA-Zà-ỹÀ-Ỹ0-9])\s+([,.;:?])")
    _PUNCT_SPACE_AFTER_COMMA = re.compile(r"([,;:])([a-zA-Zà-ỹÀ-Ỹ])")
    _PUNCT_SPACE_AFTER_DOT = re.compile(r"\.([A-ZÀ-Ỹ])")
    _PUNCT_SPACE_AFTER_QUESTION = re.compile(r"\?([a-zA-Zà-ỹÀ-Ỹ])")

    # 5. Danh sách từ viết tắt ngân hàng đã biên dịch sẵn regex
    _BUSINESS_ACRONYMS: ClassVar[list[tuple[re.Pattern[str], str]]] = _load_bank_acronyms()

    @classmethod
    def normalize(cls, text: str, expand_acronyms: bool = True) -> str:
        """
        Chuẩn hóa văn bản tiếng Việt toàn diện & tối ưu:
        - Bảo vệ Email (khanh@ggroup.vn), URL, Mã hồ sơ (PUR/2026/000088).
        - Xóa rác ký tự đặc biệt lặp/hỗn hợp (@#!#! -> xóa sạch).
        - Loại bỏ dấu cảm thán (!) để tối ưu độ chính xác Vector Search.
        - Khử lặp ký tự kéo dài (Anhhhhhh -> Anh).
        - Chuẩn hóa dấu thanh và từ ngữ qua underthesea.
        - Mở rộng từ viết tắt ngân hàng (TTr -> Tờ trình, STK -> Số tài khoản...).
        """
        if not text:
            return ""

        # 1. Unicode NFC & lọc ký tự ẩn zero-width
        text = unicodedata.normalize("NFC", text)
        text = cls._ZERO_WIDTH_PATTERN.sub("", text)

        # 2. Lọc cụm ký tự rác & loại bỏ dấu cảm thán
        text = cls._JUNK_SYMBOLS_PATTERN.sub(" ", text)
        text = cls._ISOLATED_SYMBOLS_PATTERN.sub(" ", text)
        text = text.replace("!", " ")

        # 3. Khử lặp ký tự kéo dài & rút gọn dấu câu lặp
        text = cls._ELONGATION_PATTERN.sub(r"\1", text)
        text = cls._PUNCT_REPEAT_PATTERN.sub(r"\1", text)

        # 4. Chuẩn hóa dấu thanh và từ ngữ bằng underthesea
        if text_normalize is not None:
            try:
                text = text_normalize(text)
            except Exception:
                pass

        # 5. Chuẩn hóa khoảng trắng và dòng trống
        lines = [cls._HORIZ_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
        text = "\n".join(lines)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = cls._MULTIPLE_NEWLINES.sub("\n\n", text)

        # 6. Mở rộng từ viết tắt ngân hàng
        if expand_acronyms:
            for pattern, replacement in cls._BUSINESS_ACRONYMS:
                text = pattern.sub(replacement, text)

        # 7. Chuẩn hóa khoảng trắng quanh dấu câu hợp lệ (?, ., ,)
        text = cls._PUNCT_ATTACH_BEFORE.sub(r"\1\2", text)
        text = cls._PUNCT_SPACE_AFTER_COMMA.sub(r"\1 \2", text)
        text = cls._PUNCT_SPACE_AFTER_DOT.sub(r". \1", text)
        text = cls._PUNCT_SPACE_AFTER_QUESTION.sub(r"? \1", text)

        # 8. Dọn dẹp ký tự thừa ở đầu và cuối chuỗi
        text = cls._LEADING_PUNCT_PATTERN.sub("", text)
        return cls._HORIZ_WHITESPACE.sub(" ", text).strip(" /\\_-")


def normalize_for_match(text: str) -> str:
    """
    Chuyển văn bản thành chữ thường, loại bỏ dấu tiếng Việt để làm Cache Key / Match.
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    builder = [
        "d" if char in ("đ", "\u0111", "Đ", "\u0110") else char
        for char in normalized
        if unicodedata.category(char) != "Mn"
    ]
    composed = unicodedata.normalize("NFC", "".join(builder))
    return " ".join(composed.split())
