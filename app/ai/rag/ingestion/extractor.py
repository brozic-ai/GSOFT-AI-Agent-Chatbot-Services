"""
Module trích xuất nội dung văn bản từ các định dạng file (File Text Extractor).
Hỗ trợ PDF, PPTX, DOCX, XLSX, CSV, Plain Text theo mô hình PageContent (page/slide/sheet metadata).
Tuân thủ Clean Architecture & DDD Standard Enterprise.
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".log", ".json", ".xml", ".html", ".htm"}


@dataclass
class PageContent:
    """
    Đại diện cho nội dung trích xuất của từng trang (page / slide / sheet).
    Dễ dàng mở rộng cho Vision OCR (Qwen VL 7B Multimodal) qua trường image_bytes.
    """

    text: str
    page_number: int  # 1-indexed
    metadata: dict[str, Any] = field(default_factory=dict)
    image_bytes: bytes | None = None  # Dành sẵn cho Vision OCR


class FileTextExtractor:
    """Trích xuất nội dung văn bản từ các định dạng file đĩa (Async API)."""

    async def extract(self, file_path: str, file_name: str) -> list[PageContent]:
        """
        Trích xuất danh sách các trang/slide/sheet văn bản kèm metadata.

        Args:
            file_path: Đường dẫn tuyệt đối tới file tạm trên đĩa.
            file_name: Tên file gốc (dùng để xác định extension).
        """
        ext = Path(file_name).suffix.lower()
        kind = self._detect_file_kind(file_path, ext)
        logger.info(
            "[EXTRACT] Parsing file='%s' with extension='%s' kind='%s'",
            file_name,
            ext,
            kind,
        )

        try:
            if kind == "pdf":
                return self._extract_pdf(file_path, file_name)
            elif kind == "pptx":
                return self._extract_pptx(file_path, file_name)
            elif kind == "docx":
                return self._extract_docx(file_path, file_name)
            elif kind == "xlsx":
                return self._extract_excel(file_path, file_name)
            elif kind == "csv":
                return self._extract_csv(file_path, file_name)
            elif kind == "text":
                return self._extract_plain_text(file_path, file_name)
            elif kind == "ole_doc":
                logger.warning(
                    "[WARN] Legacy .doc/OLE file '%s' is not supported by python-docx. "
                    "Please convert it to .docx before ingestion.",
                    file_name,
                )
                return [
                    PageContent(
                        text="",
                        page_number=1,
                        metadata={"source": file_name, "page": 1},
                    )
                ]
            else:
                logger.warning(
                    "[WARN] Unsupported binary file '%s'. Skipping text extraction.",
                    file_name,
                )
                return [
                    PageContent(
                        text="",
                        page_number=1,
                        metadata={"source": file_name, "page": 1},
                    )
                ]
        except Exception:
            logger.exception("[FAIL] Error parsing file '%s' (%s).", file_name, ext)
            if not self._looks_binary(file_path):
                logger.warning(
                    "[WARN] Falling back to safe text decoding for '%s'.", file_name
                )
                return self._extract_plain_text(file_path, file_name)
            logger.warning(
                "[WARN] Not falling back to text for binary file '%s'.", file_name
            )
            return [
                PageContent(
                    text="", page_number=1, metadata={"source": file_name, "page": 1}
                )
            ]

    def _detect_file_kind(self, path: str, ext: str) -> str:
        with open(path, "rb") as f:
            header = f.read(8)

        if header.startswith(b"%PDF"):
            return "pdf"
        if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "ole_doc"
        if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            if ext == ".pptx":
                return "pptx"
            if ext == ".xlsx":
                return "xlsx"
            return "docx"
        if ext == ".csv":
            return "csv"
        if ext in TEXT_EXTENSIONS or not self._looks_binary(path):
            return "text"
        return "binary"

    def _looks_binary(self, path: str) -> bool:
        with open(path, "rb") as f:
            sample = f.read(4096)
        if not sample:
            return False
        if b"\x00" in sample:
            return True
        control_bytes = re.findall(rb"[\x01-\x08\x0b\x0c\x0e-\x1f]", sample)
        return len(control_bytes) / len(sample) > 0.10

    def _read_text_safely(self, path: str) -> str:
        with open(path, "rb") as f:
            raw = f.read()
        if not raw:
            return ""

        for encoding in ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue

        return raw.decode("utf-8", errors="replace")

    def _extract_pdf(self, path: str, file_name: str) -> list[PageContent]:
        """Trích xuất PDF từng trang bằng pypdf."""
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages: list[PageContent] = []
        total_pages = len(reader.pages)

        for page_idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()

            # [FUTURE HOOK] Vision OCR cho trang PDF chỉ có hình ảnh:
            # if not text and settings.INGESTION_ENABLE_VISION_OCR:
            #     image_bytes = self._render_pdf_page_to_image(path, page_idx)
            #     text = await self._ocr_with_vision(image_bytes)

            pages.append(
                PageContent(
                    text=text,
                    page_number=page_idx,
                    metadata={
                        "source": file_name,
                        "page": page_idx,
                        "total_pages": total_pages,
                    },
                )
            )

        logger.info("[EXTRACT] Extracted %d pages from PDF '%s'", len(pages), file_name)
        return pages

    def _extract_pptx(self, path: str, file_name: str) -> list[PageContent]:
        """
        Trích xuất PPTX từng slide bằng python-pptx theo cơ chế Atomic Slide & Slide Aggregation.
        Nếu Slide N quá ngắn (< 200 ký tự), tự động gộp nội dung của Slide N vào Slide N+1
        hoặc gộp theo cụm slide liên kề để đảm bảo trọn vẹn ngữ cảnh cho vector embedding.
        """
        from pptx import Presentation

        prs = Presentation(path)
        total_slides = len(prs.slides)
        min_slide_chars = getattr(settings, "RAG_MIN_SLIDE_CHARS", 200)

        # 1. Trích xuất thô từng slide ban đầu
        raw_slides: list[dict[str, Any]] = []
        for slide_idx, slide in enumerate(prs.slides, start=1):
            title = ""
            if slide.shapes.title and slide.shapes.title.text:
                title = slide.shapes.title.text.strip()

            body_lines: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        line = para.text.strip()
                        # Tránh lặp lại tiêu đề slide trong phần thân
                        if line and line != title:
                            body_lines.append(line)

            raw_slides.append(
                {
                    "slide_idx": slide_idx,
                    "title": title,
                    "body_lines": body_lines,
                }
            )

        # 2. Thuật toán Slide Aggregation: Gộp slide ngắn (< 200 chars) vào slide kế tiếp N+1
        aggregated_groups: list[dict[str, Any]] = []
        buf_indices: list[int] = []
        buf_titles: list[str] = []
        buf_texts: list[str] = []

        for s in raw_slides:
            s_idx = s["slide_idx"]
            s_title = s["title"]
            lines = s["body_lines"]

            slide_parts: list[str] = []
            if s_title:
                slide_parts.append(f"### Tiêu đề: {s_title}")
            if lines:
                slide_parts.extend(lines)

            slide_body = "\n".join(slide_parts).strip()

            buf_indices.append(s_idx)
            if s_title and s_title not in buf_titles:
                buf_titles.append(s_title)
            if slide_body:
                buf_texts.append(slide_body)

            total_buf_len = sum(len(t) for t in buf_texts)

            # Nếu tổng ký tự tích lũy đạt ngưỡng >= min_slide_chars thì đóng gói group
            if total_buf_len >= min_slide_chars:
                aggregated_groups.append(
                    {
                        "indices": list(buf_indices),
                        "titles": list(buf_titles),
                        "body": "\n\n".join(buf_texts).strip(),
                    }
                )
                buf_indices.clear()
                buf_titles.clear()
                buf_texts.clear()

        # Xử lý phần dư trong buffer nếu slide cuối cùng < min_slide_chars
        if buf_texts:
            if aggregated_groups:
                # Gộp vào slide group liền trước
                last_grp = aggregated_groups[-1]
                last_grp["indices"].extend(buf_indices)
                for t in buf_titles:
                    if t not in last_grp["titles"]:
                        last_grp["titles"].append(t)
                last_grp["body"] = (
                    last_grp["body"] + "\n\n" + "\n\n".join(buf_texts)
                ).strip()
            else:
                # Trường hợp đặc biệt: toàn bộ file PPTX có nội dung rất ngắn
                aggregated_groups.append(
                    {
                        "indices": list(buf_indices),
                        "titles": list(buf_titles),
                        "body": "\n\n".join(buf_texts).strip(),
                    }
                )

        # 3. Đóng gói thành các PageContent với tiền tố ngữ cảnh chuẩn hóa
        pages: list[PageContent] = []
        for grp in aggregated_groups:
            indices = grp["indices"]
            start_slide = indices[0]
            end_slide = indices[-1]
            slide_label = (
                f"{start_slide}-{end_slide}"
                if start_slide != end_slide
                else str(start_slide)
            )
            combined_title = " | ".join(grp["titles"]) if grp["titles"] else ""

            # Tiền tố: [Tài liệu: {file_name}] [Slide {slide_label}/{total_slides}]
            prefix_header = (
                f"[Tài liệu: {file_name}] [Slide {slide_label}/{total_slides}]"
            )
            full_text = f"{prefix_header}\n{grp['body']}".strip()

            pages.append(
                PageContent(
                    text=full_text,
                    page_number=start_slide,
                    metadata={
                        "source": file_name,
                        "slide": slide_label,
                        "slide_start": start_slide,
                        "slide_end": end_slide,
                        "slide_title": combined_title,
                        "total_slides": total_slides,
                        "is_atomic_slide": True,
                        "is_aggregated": len(indices) > 1,
                        "aggregated_slide_count": len(indices),
                        "content_format": "pptx_slide",
                    },
                )
            )

        logger.info(
            "[EXTRACT] Extracted %d atomic/aggregated slides from %d original slides in PPTX '%s'",
            len(pages),
            total_slides,
            file_name,
        )
        return pages

    def _extract_docx(self, path: str, file_name: str) -> list[PageContent]:
        """Trích xuất DOCX nhóm theo heading/sections bằng python-docx có fallback an toàn."""
        import docx

        doc_obj = None
        try:
            doc_obj = docx.Document(path)
        except Exception as docx_ex:  # noqa: BLE001
            logger.warning(
                "[WARN] python-docx failed for '%s': %s. Trying zip/XML fallback...",
                file_name,
                docx_ex,
            )
            fallback_text = ""
            try:
                import zipfile

                with zipfile.ZipFile(path) as z:
                    if "word/document.xml" in z.namelist():
                        xml_bytes = z.read("word/document.xml")
                        xml_str = xml_bytes.decode("utf-8", errors="replace")
                        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml_str)
                        if texts:
                            fallback_text = "\n".join(
                                [t.strip() for t in texts if t.strip()]
                            )
            except Exception as zip_ex:  # noqa: BLE001
                logger.warning(
                    "[WARN] Zip XML fallback also failed for '%s': %s", file_name, zip_ex
                )

            # Tuyệt đối không đọc file nhị phân zip bằng open(path, "rb") decode utf-8
            # để tránh đẩy hàng loạt chunk rác PK\x03\x04 vào CSDL
            if not fallback_text:
                logger.error(
                    "[FAIL] Không thể trích xuất văn bản từ file DOCX '%s'. Đánh dấu tài liệu không hợp lệ thay vì đọc nhị phân rác.",
                    file_name,
                )
                return [
                    PageContent(
                        text="",
                        page_number=1,
                        metadata={
                            "source": file_name,
                            "section": 1,
                            "error": "unreadable_docx",
                        },
                    )
                ]

            return [
                PageContent(
                    text=fallback_text.strip(),
                    page_number=1,
                    metadata={"source": file_name, "section": 1},
                )
            ]

        pages: list[PageContent] = []
        current_section_title = ""
        current_texts: list[str] = []
        section_idx = 1

        for p in doc_obj.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            if p.style and p.style.name.startswith("Heading"):
                if current_texts:
                    pages.append(
                        PageContent(
                            text="\n".join(current_texts),
                            page_number=section_idx,
                            metadata={
                                "source": file_name,
                                "section": section_idx,
                                "section_title": current_section_title,
                            },
                        )
                    )
                    section_idx += 1
                    current_texts = []
                current_section_title = text

            current_texts.append(text)

        if current_texts:
            pages.append(
                PageContent(
                    text="\n".join(current_texts),
                    page_number=section_idx,
                    metadata={
                        "source": file_name,
                        "section": section_idx,
                        "section_title": current_section_title,
                    },
                )
            )

        if not pages:
            # Fallback nếu không có paragraph style
            full_text = "\n".join(
                [p.text.strip() for p in doc_obj.paragraphs if p.text.strip()]
            )
            pages.append(
                PageContent(
                    text=full_text,
                    page_number=1,
                    metadata={"source": file_name, "section": 1},
                )
            )

        logger.info(
            "[EXTRACT] Extracted %d sections from DOCX '%s'", len(pages), file_name
        )
        return pages

    def _extract_excel(self, path: str, file_name: str) -> list[PageContent]:
        """Trích xuất XLSX (openpyxl) từng sheet dạng Markdown table (không hỗ trợ .xls)."""
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True)
        pages: list[PageContent] = []

        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue

            md_lines: list[str] = [f"### Sheet: {sheet_name}"]
            for row_idx, row in enumerate(rows):
                str_cells = [
                    str(cell).strip() if cell is not None else "" for cell in row
                ]
                if not any(str_cells):
                    continue
                line = "| " + " | ".join(str_cells) + " |"
                md_lines.append(line)
                if row_idx == 0:
                    md_lines.append("| " + " | ".join(["---"] * len(str_cells)) + " |")

            sheet_text = "\n".join(md_lines).strip()
            pages.append(
                PageContent(
                    text=sheet_text,
                    page_number=sheet_idx,
                    metadata={
                        "source": file_name,
                        "sheet_name": sheet_name,
                        "page": sheet_idx,
                    },
                )
            )

        wb.close()
        logger.info(
            "[EXTRACT] Extracted %d sheets from XLSX '%s'", len(pages), file_name
        )
        return pages

    def _extract_csv(self, path: str, file_name: str) -> list[PageContent]:
        """Trích xuất CSV dạng Markdown table."""
        content = self._read_text_safely(path)
        reader = csv.reader(content.splitlines())
        md_lines: list[str] = []
        for idx, row in enumerate(reader):
            if not row:
                continue
            line = "| " + " | ".join([c.strip() for c in row]) + " |"
            md_lines.append(line)
            if idx == 0:
                md_lines.append("| " + " | ".join(["---"] * len(row)) + " |")

        csv_text = "\n".join(md_lines).strip()
        return [
            PageContent(
                text=csv_text,
                page_number=1,
                metadata={"source": file_name, "page": 1},
            )
        ]

    def _extract_plain_text(self, path: str, file_name: str) -> list[PageContent]:
        """Trích xuất Plain text file."""
        content = self._read_text_safely(path).strip()
        return [
            PageContent(
                text=content,
                page_number=1,
                metadata={"source": file_name, "page": 1},
            )
        ]

    # ─── FUTURE: Vision OCR Hook via Qwen VL 7B (Ollama VM) ────────────────
    #
    # async def _ocr_with_vision(self, image_bytes: bytes) -> str:
    #     """
    #     Trích xuất văn bản từ hình ảnh bằng mô hình Multimodal Qwen 2.5 VL 7B qua Ollama API.
    #     Kích hoạt bằng cách bật INGESTION_ENABLE_VISION_OCR=True trong file .env.
    #     """
    #     import base64
    #     import httpx
    #
    #     b64 = base64.b64encode(image_bytes).decode()
    #     payload = {
    #         "model": settings.LLM_MODEL,  # qwen2.5vl:7b
    #         "messages": [
    #             {
    #                 "role": "user",
    #                 "content": [
    #                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    #                     {"type": "text", "text": "Hãy trích xuất toàn bộ văn bản có trong hình ảnh này."},
    #                 ],
    #             }
    #         ],
    #     }
    #     async with httpx.AsyncClient(timeout=90.0) as client:
    #         res = await client.post(f"{settings.LLM_BASE_URL}/chat/completions", json=payload)
    #         res.raise_for_status()
    #         return res.json()["choices"][0]["message"]["content"]
