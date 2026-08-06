"""
Module trích xuất nội dung văn bản từ các định dạng file (File Text Extractor).
Tách riêng khỏi DocumentService theo chuẩn RAG Clean Architecture.
"""

import logging

logger = logging.getLogger(__name__)


class FileTextExtractor:
    """Trích xuất nội dung văn bản từ file đĩa theo định dạng."""

    def extract(self, file_path: str, file_name: str) -> str:
        """
        Trích xuất chuỗi văn bản từ file.

        Args:
            file_path: Đường dẫn tuyệt đối tới file tạm trên đĩa.
            file_name: Tên file gốc (dùng để kiểm tra extension).
        """
        if file_name.lower().endswith('.docx'):
            return self._extract_docx(file_path)
        else:
            return self._extract_plain_text(file_path)

    def _extract_docx(self, path: str) -> str:
        try:
            import docx
            doc_obj = docx.Document(path)
            text = "\n".join([p.text for p in doc_obj.paragraphs if p.text.strip()])
            return text
        except Exception as docx_ex:
            logger.warning("[WARN] Failed to parse docx using python-docx: %s. Falling back to plain text.", docx_ex)
            return self._extract_plain_text(path)

    def _extract_plain_text(self, path: str) -> str:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
