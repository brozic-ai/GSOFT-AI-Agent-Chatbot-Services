"""
Subsystem Phân tách Văn bản (Text Chunking Subsystem) cho RAG AI System.
Sử dụng RecursiveCharacterTextSplitter để phân tách văn bản theo ngữ nghĩa thay cho naive slicing.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """Kết quả phân tách văn bản kèm theo metadata ngữ cảnh tiêu đề."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TextChunker:
    """Tách văn bản thành các chunks ngữ nghĩa sử dụng RecursiveCharacterTextSplitter và Heading Context Breadcrumbs."""

    _HEADING_PATTERN = re.compile(
        r"^(#{1,6}\s+|(?:[IVXLCDM]+\b(?:\.\d+)*\.?|\d+(?:\.\d+)*\.?)\s+)([^\n]+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        chunk_by_tokens: bool | None = None,
    ):
        self.chunk_size = chunk_size or getattr(settings, "RAG_CHUNK_SIZE", 800)
        self.chunk_overlap = chunk_overlap or getattr(settings, "RAG_CHUNK_OVERLAP", 100)
        self.chunk_by_tokens = (
            chunk_by_tokens
            if chunk_by_tokens is not None
            else getattr(settings, "RAG_CHUNK_BY_TOKENS", True)
        )

        if self.chunk_by_tokens:
            try:
                self.splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    separators=["\n\n", "\n", ".", " ", ""],
                )
            except Exception as ex:
                logger.warning(
                    "[CHUNKER] Không thể khởi tạo tiktoken encoder (%s). Fallback về RecursiveCharacterTextSplitter ký tự.",
                    ex,
                )
                self.splitter = RecursiveCharacterTextSplitter(
                    chunk_size=int(self.chunk_size * 3.5),
                    chunk_overlap=int(self.chunk_overlap * 3.5),
                    separators=["\n\n", "\n", ".", " ", ""],
                    length_function=len,
                )
        else:
            self.splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ".", " ", ""],
                length_function=len,
            )

    def split_text(self, text: str) -> list[str]:
        """
        Phân tách chuỗi văn bản thành danh sách đoạn (chunks).

        Args:
            text: Chuỗi văn bản thô đầu vào.

        Returns:
            Danh sách các chuỗi chunk ngữ nghĩa.
        """
        if not text or not text.strip():
            return []
        chunks = self.splitter.split_text(text)
        logger.debug(
            "[CHUNK] Split text (len=%d) into %d chunks (size=%d, overlap=%d)",
            len(text),
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    def split_markdown_with_context(self, text: str) -> list[ChunkResult]:
        """
        Phân tách văn bản Markdown có bảo toàn ngữ cảnh tiêu đề (Heading Context Breadcrumbs).

        Mỗi chunk sinh ra sẽ được tự động đính kèm tiền tố ngữ cảnh:
        [Ngữ cảnh: IV.3 Quản lý loại hàng hóa > IV.3.2 Quy tắc chung và ràng buộc]

        Args:
            text: Chuỗi văn bản Markdown thô.

        Returns:
            Danh sách ChunkResult gồm chuỗi text có tiền tố ngữ cảnh và dict metadata.
        """
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        sections: list[tuple[list[dict[str, Any]], list[str]]] = []
        stack: list[dict[str, Any]] = []
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            m = self._HEADING_PATTERN.match(stripped)
            if m:
                if current_lines:
                    sections.append((list(stack), current_lines))
                    current_lines = []
                prefix, _ = m.groups()
                if prefix.startswith("#"):
                    level = len(prefix.strip())
                else:
                    level = max(1, prefix.strip().count("."))
                clean_heading = stripped.lstrip("#").strip()
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                stack.append({"level": level, "heading": clean_heading})
                current_lines.append(stripped)
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((list(stack), current_lines))

        results: list[ChunkResult] = []
        for st, body_lines in sections:
            section_path = " > ".join(item["heading"] for item in st)
            section = st[-1]["heading"] if st else ""
            heading_level = st[-1]["level"] if st else 0
            raw_heading = st[-1]["heading"] if st else ""
            body_text = "\n".join(body_lines).strip()
            if not body_text:
                continue

            raw_chunks = self.splitter.split_text(body_text)
            for chunk in raw_chunks:
                chunk_str = chunk.strip()
                if not chunk_str:
                    continue
                if chunk_str.startswith("[Ngữ cảnh:"):
                    final_text = chunk_str
                elif section_path:
                    final_text = f"[Ngữ cảnh: {section_path}]\n{chunk_str}"
                else:
                    final_text = chunk_str

                results.append(
                    ChunkResult(
                        text=final_text,
                        metadata={
                            "section": section,
                            "section_path": section_path,
                            "heading_level": heading_level,
                            "raw_heading": raw_heading,
                        },
                    )
                )

        logger.debug(
            "[CHUNK] split_markdown_with_context generated %d enriched chunks.",
            len(results),
        )
        return results
