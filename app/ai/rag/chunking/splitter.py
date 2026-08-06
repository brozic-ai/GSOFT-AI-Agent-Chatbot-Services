"""
Subsystem Phân tách Văn bản (Text Chunking Subsystem) cho RAG AI System.
Sử dụng RecursiveCharacterTextSplitter để phân tách văn bản theo ngữ nghĩa thay cho naive slicing.
"""

import logging
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)


class TextChunker:
    """Tách văn bản thành các chunks ngữ nghĩa sử dụng RecursiveCharacterTextSplitter."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
            length_function=len,
        )

    def split_text(self, text: str) -> List[str]:
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
        logger.debug("[CHUNK] Split text (len=%d) into %d chunks (size=%d, overlap=%d)",
                     len(text), len(chunks), self.chunk_size, self.chunk_overlap)
        return chunks
