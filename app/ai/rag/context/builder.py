"""
RAG Context Builder & Dynamic Max Tokens Subsystem (app/ai/rag/context/builder.py).

Chịu trách nhiệm:
1. Làm sạch rác (LaTeX, divider lines, header/footer lặp).
2. Khử trùng lặp Exact & Near-duplicate (>= 85% line overlap trong cùng nguồn/trang).
3. Cắt tỉa chunk vượt quá kích thước tối đa (procedure 5k, image UI 1.5k, general 2k).
4. Ép trần tổng ngữ cảnh RAG tối đa 18,000 ký tự.
5. Format định dạng [ĐOẠN n - <label>] và trả về used_metadatas / used_citations chuẩn xác cho SSE.
6. Tính toán max_tokens động theo số bước quy trình trong context.
"""

import logging
import re
from typing import Any

from app.ai.rag.text.cleaner import TextArtifactCleaner
from app.ai.rag.text.normalizer import normalize_for_match
from app.core.config import settings

import urllib.parse

logger = logging.getLogger(__name__)


def _clean_source_name(raw_source: Any) -> str:
    """Giải mã URL Encoding (%E1%BB...) và ký tự '+' thành tiếng Việt có dấu chuẩn."""
    if not raw_source:
        return "Tài liệu"
    source_str = str(raw_source).strip()
    try:
        # 解码 URL percent encoding và dấu '+' thành khoảng trắng
        decoded = urllib.parse.unquote_plus(source_str)
        return decoded
    except Exception:
        return source_str


def _get_citation_identity(meta: dict[str, Any]) -> str:
    """Tạo chuỗi định danh duy nhất cho citation dựa trên metadata."""
    source = _clean_source_name(meta.get("source") or meta.get("file_name"))
    page = str(
        meta.get("page") or meta.get("page_number") or meta.get("slide") or ""
    ).strip()
    section = str(
        meta.get("section") or meta.get("slide_title") or meta.get("page_title") or ""
    ).strip()
    return f"{source}|{page}|{section}"


def _build_citation_label(meta: dict[str, Any]) -> str:
    """Tạo nhãn trích dẫn hiển thị cho từng chunk trong prompt."""
    source = _clean_source_name(meta.get("source") or meta.get("file_name"))
    parts = [source]
    page = meta.get("page") or meta.get("page_number") or meta.get("slide")
    if page:
        parts.append(f"Trang {page}")
    title = meta.get("slide_title") or meta.get("page_title") or meta.get("section")
    if title:
        parts.append(str(title).strip())
    return " | ".join(parts)


def _build_citation_object(meta: dict[str, Any]) -> dict[str, Any]:
    """Tạo dict trích dẫn chuẩn hóa giàu thông tin (enriched citation) gửi cho SSE client."""
    citation = {
        "source": _clean_source_name(meta.get("source") or meta.get("file_name")),
        "page": meta.get("page") or meta.get("page_number") or meta.get("slide"),
        "title": meta.get("slide_title")
        or meta.get("page_title")
        or meta.get("section"),
        "backend_document_id": meta.get("backend_document_id")
        or meta.get("backend_id")
        or meta.get("backendId"),
        "backendId": meta.get("backendId")
        or meta.get("backend_id")
        or meta.get("backend_document_id"),
    }
    for key in (
        "chunk_id",
        "id",
        "score",
        "distance",
        "similarity",
        "owner_department",
        "ownerDepartment",
        "accessScope",
    ):
        if key in meta and meta[key] is not None:
            citation[key] = meta[key]
    return citation


def truncate_to_last_space(text: str, max_chars: int) -> str:
    """Cắt bớt văn bản quá dài tại khoảng trắng gần nhất."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > int(max_chars * 0.7):
        return truncated[:last_space] + "..."
    return truncated + "..."


def count_procedure_steps(text: str) -> int:
    """Đếm số bước quy trình trong văn bản bằng Regex."""
    if not text:
        return 0
    matches = re.findall(r"\b(?:Bước|Buoc|B)\s*\d+\s*:", text, flags=re.IGNORECASE)
    return len(matches)


def determine_max_tokens(context_text: str) -> int:
    """
    Tính toán số max_tokens động dựa trên số bước quy trình trong context.
    - Không có bước: 600 tokens
    - Có bước: max(900, min(600 + step_count * 120, 1800)) tokens
    """
    step_count = count_procedure_steps(context_text)
    if step_count > 0:
        return max(900, min(600 + step_count * 120, 1800))
    return 600


class RagContextBuilder:
    """Context Builder thực hiện lọc, khử trùng lặp và đóng gói context cho RAG LLM."""

    @classmethod
    def build(
        cls,
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Xây dựng chuỗi ngữ cảnh RAG hoàn chỉnh đã qua làm sạch và khử trùng lặp.

        Returns:
            (context_text, used_metadatas, used_citations)
        """
        if not documents:
            return "", [], []

        line_occurrences: dict[str, int] = {}
        accepted_line_sets: list[tuple[set, dict[str, Any]]] = []
        seen_exact_keys: set = set()

        used_blocks: list[str] = []
        used_metadatas: list[dict[str, Any]] = []
        used_citations: list[dict[str, Any]] = []

        chunk_counter = 0

        for idx, doc in enumerate(documents):
            meta = (
                metadatas[idx]
                if idx < len(metadatas) and isinstance(metadatas[idx], dict)
                else {}
            )

            # 1. Exact deduplication check
            exact_key = f"{normalize_for_match(doc)}|{_get_citation_identity(meta)}"
            if exact_key in seen_exact_keys:
                continue
            seen_exact_keys.add(exact_key)

            # 2. Clean artifacts & trash lines
            cleaned = TextArtifactCleaner.clean(doc, line_occurrences=line_occurrences)
            if not cleaned or not cleaned.strip():
                continue

            # 3. Truncate chunk quá dài dựa trên loại nội dung (procedure step, image UI, general)
            content_kind = str(meta.get("content_kind", "")).lower()
            is_proc = (
                count_procedure_steps(cleaned) > 0
                or "instruction" in content_kind
                or "procedure" in content_kind
            )
            if is_proc:
                chunk_limit = getattr(
                    settings, "RAG_CONTEXT_PROCEDURE_CHUNK_MAX_CHARS", 5000
                )
            elif "image" in content_kind or "ui" in content_kind:
                chunk_limit = getattr(
                    settings, "RAG_CONTEXT_IMAGE_CHUNK_MAX_CHARS", 1500
                )
            else:
                chunk_limit = getattr(
                    settings, "RAG_CONTEXT_GENERAL_CHUNK_MAX_CHARS", 2000
                )

            if len(cleaned) > chunk_limit:
                cleaned = truncate_to_last_space(cleaned, chunk_limit)

            # 4. Near-duplicate check (line overlap >= threshold)
            cleaned_lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
            normalized_line_set = {normalize_for_match(l) for l in cleaned_lines}

            is_near_dup = False
            overlap_threshold = getattr(
                settings, "RAG_CONTEXT_NEAR_DUP_LINE_OVERLAP", 0.85
            )

            if len(normalized_line_set) >= 4:
                for prev_set, prev_meta in accepted_line_sets:
                    if len(prev_set) < 4:
                        continue
                    intersection = len(normalized_line_set.intersection(prev_set))
                    overlap = intersection / max(
                        len(normalized_line_set), len(prev_set)
                    )
                    if overlap >= overlap_threshold and _get_citation_identity(
                        meta
                    ) == _get_citation_identity(prev_meta):
                        is_near_dup = True
                        break

            if is_near_dup:
                logger.debug(
                    "[BUILDER] Skipped near-duplicate chunk (overlap >= %.2f)",
                    overlap_threshold,
                )
                continue

            # 5. Length constraint check đối với tổng context (tối đa 18,000 ký tự)
            temp_chunk_counter = chunk_counter + 1
            citation_label = _build_citation_label(meta)
            formatted_chunk = (
                f"[ĐOẠN {temp_chunk_counter} - {citation_label}]\n{cleaned}"
            )

            temp_blocks = used_blocks + [formatted_chunk]
            temp_context = "\n\n---\n\n".join(temp_blocks)

            max_context_chars = getattr(settings, "RAG_CONTEXT_MAX_CHARS", 18000)
            if len(temp_context) > max_context_chars:
                logger.info(
                    "[BUILDER] Discarded chunk because total context length (%d chars) would exceed %d chars limit.",
                    len(temp_context),
                    max_context_chars,
                )
                continue

            # Chấp nhận chunk
            chunk_counter = temp_chunk_counter
            used_blocks.append(formatted_chunk)
            used_metadatas.append(meta)
            used_citations.append(_build_citation_object(meta))
            accepted_line_sets.append((normalized_line_set, meta))

        final_context_text = "\n\n---\n\n".join(used_blocks)
        logger.info(
            "[OK] [BUILDER] Context built: %d/%d chunks accepted | Total length: %d chars",
            len(used_blocks),
            len(documents),
            len(final_context_text),
        )

        return final_context_text, used_metadatas, used_citations
