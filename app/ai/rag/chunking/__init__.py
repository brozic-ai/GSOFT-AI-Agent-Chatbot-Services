"""
Chunking Package cho RAG System.
Phân tách văn bản theo ngữ nghĩa (Semantic & Recursive Chunking).
"""

from app.ai.rag.chunking.splitter import ChunkResult, TextChunker

__all__ = ["ChunkResult", "TextChunker"]
