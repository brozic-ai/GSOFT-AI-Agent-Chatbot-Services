"""
Unit Tests kiểm tra các cải tiến RAG trong Local AI Agent:
1. VietnameseNormalizer & normalize_for_match
2. TextArtifactCleaner
3. RagContextBuilder & determine_max_tokens
"""

import unicodedata
import unittest

from app.ai.rag.chunking import TextChunker
from app.ai.rag.context.builder import RagContextBuilder, determine_max_tokens
from app.ai.rag.text.cleaner import TextArtifactCleaner
from app.ai.rag.text.normalizer import VietnameseNormalizer, normalize_for_match


class TestRagImprovements(unittest.TestCase):
    def test_vietnamese_normalizer_nfc(self):
        # NFD input: "h" + "o" + "̀" + "a" -> NFC "hòa"
        nfd_str = unicodedata.normalize("NFD", "hoà")
        normalized = VietnameseNormalizer.normalize(nfd_str, expand_acronyms=True)
        self.assertEqual(normalized, "hòa")

    def test_vietnamese_normalizer_acronyms(self):
        text = "Chuyển tiền qua STK và TK cá nhân của KH, lập TTr mua sắm VPP"
        res = VietnameseNormalizer.normalize(text, expand_acronyms=True)
        self.assertIn("Số tài khoản", res)
        self.assertIn("Tài khoản cá nhân", res)
        self.assertIn("Khách hàng", res)
        self.assertIn("Tờ trình", res)
        self.assertIn("Văn phòng phẩm", res)

    def test_vietnamese_normalizer_noise_and_deduplication(self):
        text = "@#!#! Hello    Xin chào Anhhhhhh. khanh@ggroup.vn/"
        res = VietnameseNormalizer.normalize(text, expand_acronyms=True)
        self.assertEqual(res, "Hello Xin chào Anh. khanh@ggroup.vn")

    def test_vietnamese_normalizer_zero_width(self):
        text = "Xin\u200bchào\ufeffthế giới"
        res = VietnameseNormalizer.normalize(text, expand_acronyms=True)
        self.assertEqual(res, "Xinchàothế giới")

    def test_normalize_for_match(self):
        text = "Thủ Tục Đăng Ký Tài Khoản KH!"
        res = normalize_for_match(text)
        self.assertEqual(res, "thu tuc dang ky tai khoan kh!")

    def test_text_artifact_cleaner(self):
        raw = (
            "Line 1: Bình thường\n"
            "\\begin{equation}\n"
            "x + y = z\n"
            "\\end{equation}\n"
            "==================\n"
            "Header lặp lại\n"
            "Header lặp lại\n"
            "Header lặp lại\n"
            "Line 2: Hợp lệ\n"
        )
        cleaned = TextArtifactCleaner.clean(raw)
        lines = cleaned.splitlines()
        self.assertIn("Line 1: Bình thường", lines)
        self.assertNotIn("\\begin{equation}", lines)
        self.assertNotIn("==================", lines)
        self.assertEqual(lines.count("Header lặp lại"), 2)
        self.assertIn("Line 2: Hợp lệ", lines)

    def test_determine_max_tokens(self):
        text_no_steps = "Đây là tài liệu thông thường không có các bước quy trình."
        self.assertEqual(determine_max_tokens(text_no_steps), 600)

        text_with_steps = (
            "Bước 1: Mở trình duyệt.\n"
            "Bước 2: Nhập địa chỉ hệ thống.\n"
            "Bước 3: Đăng nhập tài khoản.\n"
            "Bước 4: Chọn menu Mua sắm.\n"
        )
        # 600 + 4 * 120 = 1080 -> max(900, min(1080, 1800)) = 1080
        self.assertEqual(determine_max_tokens(text_with_steps), 1080)

    def test_rag_context_builder_dedup(self):
        docs = [
            "Đoạn văn bản quy trình mua sắm số 1.",
            "Đoạn văn bản quy trình mua sắm số 1.",  # Exact duplicate
            "Nội dung khác về tài sản công ty.",
        ]
        metas = [
            {"source": "HD.docx", "page": 1},
            {"source": "HD.docx", "page": 1},
            {"source": "HD.docx", "page": 2},
        ]

        context_str, used_metas, used_citations = RagContextBuilder.build(docs, metas)

        self.assertEqual(len(used_metas), 2)
        self.assertEqual(len(used_citations), 2)
        self.assertIn("Đoạn văn bản quy trình mua sắm số 1.", context_str)
        self.assertIn("Nội dung khác về tài sản công ty.", context_str)

    def test_text_chunker_markdown_breadcrumbs(self):
        md_text = (
            "# IV.3 Quản lý loại hàng hóa\n"
            "Tổng quan về quản lý loại hàng hóa.\n\n"
            "## IV.3.2 Quy tắc chung và ràng buộc\n"
            "Ở các Lưới dữ liệu đều có thể bấm header của mỗi cột dữ liệu để sắp xếp Lưới dữ liệu theo thứ tự tăng dần.\n"
        )
        chunker = TextChunker(chunk_size=300, chunk_overlap=50)
        results = chunker.split_markdown_with_context(md_text)

        self.assertEqual(len(results), 2)

        # Chunk 1 (Heading 1)
        self.assertTrue(
            results[0].text.startswith("[Ngữ cảnh: IV.3 Quản lý loại hàng hóa]")
        )
        self.assertEqual(
            results[0].metadata["section_path"], "IV.3 Quản lý loại hàng hóa"
        )

        # Chunk 2 (Heading 2)
        self.assertTrue(
            results[1].text.startswith(
                "[Ngữ cảnh: IV.3 Quản lý loại hàng hóa > IV.3.2 Quy tắc chung và ràng buộc]"
            )
        )
        self.assertEqual(
            results[1].metadata["section_path"],
            "IV.3 Quản lý loại hàng hóa > IV.3.2 Quy tắc chung và ràng buộc",
        )

    def test_text_chunker_roman_numeral_breadcrumbs(self):
        text = (
            "IV.3. Quản lý loại hàng hóa\n"
            "Tổng quan về quản lý loại hàng hóa.\n\n"
            "IV.3.2. Quy tắc chung và ràng buộc\n"
            "Ở các Lưới dữ liệu đều có thể bấm header của mỗi cột dữ liệu để sắp xếp.\n"
        )
        chunker = TextChunker(chunk_size=300, chunk_overlap=50)
        results = chunker.split_markdown_with_context(text)

        self.assertEqual(len(results), 2)
        self.assertTrue(
            results[0].text.startswith("[Ngữ cảnh: IV.3. Quản lý loại hàng hóa]")
        )
        self.assertEqual(
            results[0].metadata["section_path"], "IV.3. Quản lý loại hàng hóa"
        )
        self.assertTrue(
            results[1].text.startswith(
                "[Ngữ cảnh: IV.3. Quản lý loại hàng hóa > IV.3.2. Quy tắc chung và ràng buộc]"
            )
        )
        self.assertEqual(
            results[1].metadata["section_path"],
            "IV.3. Quản lý loại hàng hóa > IV.3.2. Quy tắc chung và ràng buộc",
        )

    def test_document_service_create_ingestion_task_signature(self):
        from unittest.mock import MagicMock

        from app.modules.document.service import DocumentService

        mock_repo = MagicMock()
        mock_embed = MagicMock()
        service = DocumentService(repository=mock_repo, embedding_service=mock_embed)

        # Ensure calling create_ingestion_task with extra kwargs doesn't crash
        service.create_ingestion_task(
            task_id="task-123",
            file_name="test.docx",
            backend_document_id=74,
            file_size=1024,
            status="PENDING",
            progress_percent=0,
        )

        mock_repo.create_ingestion_task.assert_called_once_with(
            "task-123", "test.docx", 74
        )

    def test_local_embedding_fallback_disabled_by_default(self):
        from app.core.config import settings

        self.assertFalse(getattr(settings, "ENABLE_LOCAL_EMBEDDING_FALLBACK", False))

    def test_text_chunker_plain_text_fallback(self):
        plain_text = "Văn bản bình thường không chứa bất kỳ tiêu đề nào."
        chunker = TextChunker(chunk_size=300, chunk_overlap=50)

        # Markdown split with no headers
        res_md = chunker.split_markdown_with_context(plain_text)
        self.assertEqual(len(res_md), 1)
        self.assertFalse(res_md[0].text.startswith("[Ngữ cảnh:"))
        self.assertEqual(res_md[0].metadata["section_path"], "")

        # Plain split backward compatibility
        res_plain = chunker.split_text(plain_text)
        self.assertEqual(len(res_plain), 1)
        self.assertEqual(res_plain[0], plain_text)


if __name__ == "__main__":
    unittest.main()
