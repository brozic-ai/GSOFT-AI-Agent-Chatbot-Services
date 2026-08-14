"""
Module chuẩn hóa tiếng Việt cho RAG (Vietnamese Text Preprocessing).
Hỗ trợ chuẩn hóa Unicode NFC, xóa ký tự rác/zero-width, chuẩn hóa dấu thanh và mở rộng từ viết tắt.
"""

import re
import unicodedata
from typing import ClassVar


class VietnameseNormalizer:
    """
    Normalizer cho tiếng Việt trước khi embedding và chunking.
    Bảo toàn dấu tiếng Việt để giữ chất lượng vector embedding.
    Pipeline thực thi:
    Unicode NFC -> Xóa khoảng trắng thừa -> Chuẩn hóa newline -> Viết tắt (STK/TK...) -> Xóa zero-width/control chars -> Tone mark modern.
    """

    _HORIZ_WHITESPACE = re.compile(r"[ \t\f\v]+")
    _MULTIPLE_NEWLINES = re.compile(r"\n{3,}")

    _BUSINESS_ACRONYMS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"\bSTK\b"), "Số tài khoản"),
        (re.compile(r"\bTK\b"), "Tài khoản"),
        (re.compile(r"\bKH\b"), "Khách hàng"),
        (re.compile(r"\bGDV\b"), "Giao dịch viên"),
        (re.compile(r"\bPGD\b"), "Phòng giao dịch"),
        (re.compile(r"\bCN\b"), "Chi nhánh"),
    ]

    _ZERO_WIDTH_PATTERN = re.compile(
        r"[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a-\u202e\x00-\x08\x0b\x0c\x0e-\x1f]"
    )

    # Accent / Tone mark replacements (normalize old-style to modern style: hoà -> hòa)
    _TONE_REPLACEMENTS: ClassVar[list[tuple[str, str]]] = [
        ("oà", "òa"),
        ("oá", "óa"),
        ("oả", "ỏa"),
        ("oã", "õa"),
        ("oạ", "ọa"),
        ("oè", "òe"),
        ("oé", "óe"),
        ("oẻ", "ỏe"),
        ("oẽ", "õe"),
        ("oẹ", "ọe"),
        ("uỳ", "ùy"),
        ("uý", "úy"),
        ("uỷ", "ủy"),
        ("uỹ", "ũy"),
        ("uỵ", "ụy"),
        # Restore closed syllables (tone on 'a')
        ("òan", "oàn"),
        ("óan", "oán"),
        ("ỏan", "oản"),
        ("õan", "oãn"),
        ("ọan", "oạn"),
        ("òat", "oạt"),
        ("óat", "oát"),
        ("ỏat", "oắt"),
        ("ọat", "oạt"),
        ("òach", "oạch"),
        ("óach", "oách"),
        ("ọach", "oạch"),
        # Capitalized
        ("Oà", "Òa"),
        ("Oá", "Óa"),
        ("Oả", "Ỏa"),
        ("Oã", "Õa"),
        ("Oạ", "Ọa"),
        ("Oè", "Òe"),
        ("Oé", "Óe"),
        ("Oẻ", "Ỏe"),
        ("Oẽ", "Õe"),
        ("Oẹ", "Ọe"),
        ("Uỳ", "Ùy"),
        ("Uý", "Úy"),
        ("Uỷ", "Ủy"),
        ("Uỹ", "Ũy"),
        ("Uỵ", "Ụy"),
    ]

    @classmethod
    def normalize(cls, text: str, expand_acronyms: bool = True) -> str:
        """
        Chuẩn hóa văn bản tiếng Việt giữ nguyên dấu.
        """
        if not text:
            return ""

        # 1. Unicode NFC
        text = unicodedata.normalize("NFC", text)

        # 2. Trim từng dòng và gộp khoảng trắng thừa
        lines = [
            cls._HORIZ_WHITESPACE.sub(" ", line).strip() for line in text.split("\n")
        ]
        text = "\n".join(lines)

        # 3. Chuẩn hóa newline (\r\n -> \n, gộp 3+ dòng trống thành max 2 dòng trống)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = cls._MULTIPLE_NEWLINES.sub("\n\n", text)

        # 4. Viết tắt (STK, TK, KH, ...)
        if expand_acronyms:
            for pattern, replacement in cls._BUSINESS_ACRONYMS:
                text = pattern.sub(replacement, text)

        # 5. Xóa ký tự zero-width và control chars
        text = cls._ZERO_WIDTH_PATTERN.sub("", text)

        # 6. Chuẩn hóa khoảng trắng quanh dấu câu
        text = re.sub(r"([a-zA-Zà-ỹÀ-Ỹ])\s+([,.;:!?])", r"\1\2", text)
        text = re.sub(r"([,;:!?])([a-zA-Zà-ỹÀ-Ỹ])", r"\1 \2", text)
        text = re.sub(r"\.([A-ZÀ-Ỹ])", r". \1", text)

        # 7. Chuẩn hóa vị trí dấu thanh
        for old_tone, new_tone in cls._TONE_REPLACEMENTS:
            text = text.replace(old_tone, new_tone)

        return text.strip()


def normalize_for_match(text: str) -> str:
    """
    Chuyển văn bản thành chữ thường, loại bỏ hoàn toàn dấu tiếng Việt và ký tự đặc biệt.
    Dùng cho Deduplication, Cache Key embedding, Matching.
    Không dùng làm nội dung embedding trực tiếp.
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    builder = []
    for char in normalized:
        if char in ("đ", "\u0111", "Đ", "\u0110"):
            builder.append("d")
        elif unicodedata.category(char) != "Mn":
            builder.append(char)

    composed = unicodedata.normalize("NFC", "".join(builder))
    return " ".join(composed.split())
