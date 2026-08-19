"""
Module làm sạch nhiễu văn bản (Text Artifact Cleaner).
Loại bỏ dòng rác, cú pháp LaTeX, dòng không chứa alphanum (divider/pure table lines),
và loại bỏ header/footer lặp lại trong các slide/trang.
"""

import re

from app.ai.rag.text.normalizer import normalize_for_match


class TextArtifactCleaner:
    """Cleaner làm sạch rác trong văn bản chunk trước khi đưa vào Context Builder."""

    @staticmethod
    def clean(text: str, line_occurrences: dict[str, int] | None = None) -> str:
        if not text or not text.strip():
            return ""

        lines = text.splitlines()
        cleaned_lines = []
        local_occurrences = line_occurrences if line_occurrences is not None else {}

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # 1. Loại bỏ cú pháp LaTeX / Math artifacts
            if (
                "\\begin" in trimmed
                or "\\end" in trimmed
                or "\\[" in trimmed
                or "\\]" in trimmed
            ):
                continue

            # 2. Loại bỏ các dòng không chứa bất kỳ chữ cái hay chữ số nào (pure table dividers, =====, ----)
            if not any(c.isalnum() for c in trimmed):
                continue

            # 3. Deduplication theo dòng đã normalized để bỏ header/footer lặp lại
            normalized = normalize_for_match(trimmed)
            count = local_occurrences.get(normalized, 0)
            if count >= 2:
                continue

            local_occurrences[normalized] = count + 1
            cleaned_lines.append(trimmed)

        return "\n".join(cleaned_lines)

    @staticmethod
    def collapse_icon_gaps(text: str | None) -> str:
        if not text or not text.strip():
            return ""

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        pattern = r"[ \t]*\t[ \t]*| {8,}"

        def replace_match(match: re.Match) -> str:
            index = match.start()
            text_before = normalized[:index].rstrip()
            last_25 = text_before[-25:] if len(text_before) >= 25 else text_before
            has_nut = "nút" in last_25.lower() or "nut" in last_25.lower()
            return " " if has_nut else " nút "

        normalized = re.sub(pattern, replace_match, normalized)
        normalized = re.sub(r"[ \f\v]+", " ", normalized)
        normalized = re.sub(r" *\n *", "\n", normalized)
        return normalized.strip()
