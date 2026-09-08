"""
RAG Ingestion Pipeline Subsystem (app/ai/rag/ingestion/pipeline.py).

Đóng vai trò Orchestrator thực thi toàn bộ luồng xử lý ngầm (Background Tasks):
1. Extract Text từ file bất đồng bộ (PDF, PPTX, DOCX, XLSX, CSV, TXT) qua PageContent
2. Chunking ngữ nghĩa từng trang/slide/sheet với TextChunker
3. Đính kèm siêu dữ liệu RBAC + Page/Slide/Section Metadata vào từng chunk
4. Embed qua TEI Embedding Service (Mini-batching 16 chunks/lần)
5. Upsert Vector Store CSDL SQL Server (với autocommit Vector Index handling)
6. Đồng bộ trạng thái Ingest sang RagDocuments & IngestionFiles
7. Cập nhật tiến độ % và trạng thái hoàn thành vào bảng IngestionTasks
"""

import asyncio
import logging
import os
from typing import Any

from app.ai.rag.chunking import ChunkResult, TextChunker
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.ingestion.extractor import FileTextExtractor, PageContent
from app.ai.rag.text.normalizer import VietnameseNormalizer
from app.core.config import settings
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Pipeline xử lý ngầm Ingestion hoàn chỉnh."""

    def __init__(
        self, repository: DocumentRepository, embedding_service: TeiEmbeddingService
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.extractor = FileTextExtractor()
        self.chunker = TextChunker()

    def run_sync(
        self,
        task_id: str,
        temp_path: str,
        file_name: str,
        file_size: int,
        metadata: dict[str, Any],
    ) -> None:
        """
        Entry point cho FastAPI BackgroundTasks (Bridge giữa sync threadpool và async asyncio loop).
        """
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self._run_async(task_id, temp_path, file_name, file_size, metadata)
            )
        finally:
            loop.close()

    async def _run_async(
        self,
        task_id: str,
        temp_path: str,
        file_name: str,
        file_size: int,
        metadata: dict[str, Any],
    ) -> None:
        """Thực thi luồng Ingestion bất đồng bộ với báo cáo tiến độ %."""
        backend_id = str(
            metadata.get("backend_document_id")
            or metadata.get("backendId")
            or metadata.get("backend_id")
            or metadata.get("id")
            or "0"
        )
        try:
            logger.info(
                "[PIPELINE] Starting ingestion task=%s for file='%s' (backend_id=%s)...",
                task_id,
                file_name,
                backend_id,
            )

            # 1. Update status = PROCESSING, progress = 10%
            self.repository.update_ingestion_task(
                task_id, status="PROCESSING", progress_percent=10
            )
            if backend_id.isdigit() and int(backend_id) > 0:
                try:
                    self.repository.update_rag_document_status(
                        int(backend_id), "Processing", 0
                    )
                except Exception as status_ex:  # noqa: BLE001
                    logger.warning(
                        "[WARN] Could not set RagDocument ID %s to Processing: %s",
                        backend_id,
                        status_ex,
                    )

            # 2. Extract Text qua MarkItDown (nếu file là docx/pdf) hoặc qua FileTextExtractor
            pages: list[PageContent] = []
            ext = os.path.splitext(file_name)[1].lower()

            if getattr(settings, "RAG_ENABLE_MARKDOWN_CONVERSION", True) and ext in [
                ".docx",
                ".pdf",
            ]:
                try:
                    from markitdown import MarkItDown

                    md = MarkItDown()
                    result = md.convert(temp_path)
                    md_text = (
                        result.text_content
                        if hasattr(result, "text_content")
                        else str(result)
                    )
                    if md_text and md_text.strip():
                        pages = [
                            PageContent(
                                text=md_text.strip(),
                                page_number=1,
                                metadata={
                                    "source": file_name,
                                    "content_format": "markdown",
                                },
                            )
                        ]
                        logger.info(
                            "[PIPELINE] Successfully converted file '%s' via MarkItDown.",
                            file_name,
                        )
                except Exception as md_ex:  # noqa: BLE001
                    logger.warning(
                        "[PIPELINE] MarkItDown conversion failed for file '%s' (%s). Falling back to standard extractor.",
                        file_name,
                        md_ex,
                    )

            if not pages:
                pages = await self.extractor.extract(temp_path, file_name)

            self.repository.update_ingestion_task(
                task_id, status="PROCESSING", progress_percent=20
            )

            # 3. Chuẩn hóa tiếng Việt & Chunking ngữ nghĩa từng trang/slide
            access_scope = metadata.get(
                "accessScope", metadata.get("access_scope", "Public")
            )
            allowed_roles = metadata.get(
                "allowedRoles", metadata.get("allowed_roles", [])
            )
            owner_dept = metadata.get("ownerDepartment") or metadata.get(
                "owner_department"
            )

            all_chunks: list[str] = []
            all_ids: list[str] = []
            all_metadatas: list[dict[str, Any]] = []

            chunk_global_idx = 0
            for page in pages:
                raw_text = page.text
                if (
                    getattr(settings, "RAG_ENABLE_VIETNAMESE_NORMALIZATION", True)
                    and raw_text
                ):
                    raw_text = VietnameseNormalizer.normalize(
                        raw_text, expand_acronyms=True
                    )

                is_markdown = page.metadata.get("content_format") == "markdown"
                is_atomic_slide = (
                    page.metadata.get("is_atomic_slide", False)
                    or page.metadata.get("content_format") == "pptx_slide"
                )

                if is_atomic_slide:
                    # Atomic Slide Chunking: 1 Slide = 1 Vector trọn vẹn
                    # Không băm nhỏ trừ khi slide vượt quá ngưỡng 2,000 ký tự để bảo toàn tính ngữ nghĩa
                    max_slide_chars = getattr(settings, "RAG_MAX_SLIDE_CHARS", 2000)
                    if len(raw_text) <= max_slide_chars:
                        chunk_results = [
                            ChunkResult(
                                text=raw_text.strip(),
                                metadata={"slide": page.metadata.get("slide")},
                            )
                        ]
                    else:
                        raw_chunks = self.chunker.split_text(raw_text)
                        chunk_results = [
                            ChunkResult(
                                text=c, metadata={"slide": page.metadata.get("slide")}
                            )
                            for c in raw_chunks
                        ]
                elif is_markdown:
                    chunk_results = self.chunker.split_markdown_with_context(raw_text)
                else:
                    raw_chunks = self.chunker.split_text(raw_text)
                    chunk_results = [
                        ChunkResult(text=c, metadata={}) for c in raw_chunks
                    ]

                if not chunk_results and raw_text.strip():
                    chunk_results = [ChunkResult(text=raw_text.strip(), metadata={})]

                for sub_idx, res in enumerate(chunk_results):
                    chunk_id = f"{backend_id}_{page.page_number}_{sub_idx}"
                    chunk_meta = {
                        "backendId": backend_id,
                        "backend_document_id": int(backend_id)
                        if backend_id.isdigit()
                        else 0,
                        "backend_id": backend_id,
                        "source": file_name,
                        "accessScope": access_scope,
                        "allowedRoles": allowed_roles,
                        "owner_department": owner_dept,
                        "ownerDepartment": owner_dept,
                        "page": page.page_number,
                        "category": metadata.get("category"),
                        "chunk_index": chunk_global_idx,
                        **page.metadata,
                        **res.metadata,
                    }
                    all_chunks.append(res.text)
                    all_ids.append(chunk_id)
                    all_metadatas.append(chunk_meta)
                    chunk_global_idx += 1

            if not all_chunks:
                fallback_text = f"Nội dung tài liệu {file_name}"
                all_chunks = [fallback_text]
                all_ids = [f"{backend_id}_1_0"]
                all_metadatas = [
                    {
                        "backendId": backend_id,
                        "backend_document_id": int(backend_id)
                        if backend_id.isdigit()
                        else 0,
                        "backend_id": backend_id,
                        "source": file_name,
                        "accessScope": access_scope,
                        "allowedRoles": allowed_roles,
                        "owner_department": owner_dept,
                        "ownerDepartment": owner_dept,
                        "page": 1,
                        "category": metadata.get("category"),
                    }
                ]

            self.repository.update_ingestion_task(
                task_id, status="PROCESSING", progress_percent=30
            )

            # 4. Embed qua TEI Server (Mini-batching) — progress = 50%
            self.repository.update_ingestion_task(
                task_id, status="PROCESSING", progress_percent=50
            )
            embeddings = await self.embedding_service.embed_texts(all_chunks)

            # 5. Upsert vào SQL Server Vector Store — progress = 80%
            self.repository.update_ingestion_task(
                task_id, status="PROCESSING", progress_percent=80
            )
            self.repository.upsert_documents(
                ids=all_ids,
                documents=all_chunks,
                metadatas=all_metadatas,
                embeddings=embeddings,
            )

            # 6. Cập nhật trạng thái Ingest trên RagDocuments nếu có backend_id
            if backend_id.isdigit() and int(backend_id) > 0:
                self.repository.update_rag_document_status(
                    int(backend_id), "Completed", len(all_chunks)
                )

            # 7. Ghi đồng bộ log vào bảng IngestionFiles (tương thích DB cũ)
            self.repository.upsert_ingestion_file(
                file_name=file_name,
                file_size=file_size,
                status="completed",
                chunk_count=len(all_chunks),
            )

            # 8. Hoàn thành task: COMPLETED, progress = 100%
            self.repository.update_ingestion_task(
                task_id,
                status="COMPLETED",
                progress_percent=100,
                chunk_count=len(all_chunks),
            )
            logger.info(
                "[PIPELINE SUCCESS] Task=%s completed! Ingested %d chunks across %d pages.",
                task_id,
                len(all_chunks),
                len(pages),
            )

        except Exception as ex:
            logger.exception("[PIPELINE FAIL] Error during ingestion task=%s", task_id)
            # Cập nhật RagDocuments status = Failed nếu có backend_id để tránh kẹt Processing
            try:
                if backend_id.isdigit() and int(backend_id) > 0:
                    self.repository.update_rag_document_status(
                        int(backend_id), "Failed", 0, str(ex)
                    )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[WARN] Could not update RagDocuments status to Failed for doc ID %s",
                    backend_id,
                )

            # Cập nhật IngestionTask status = FAILED
            self.repository.update_ingestion_task(
                task_id,
                status="FAILED",
                progress_percent=0,
                error_message=str(ex),
            )
        finally:
            # Xóa file tạm
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug("[CLEANUP] Deleted temporary file '%s'", temp_path)
                except Exception as clean_ex:  # noqa: BLE001
                    logger.warning(
                        "[WARN] Failed to delete temp file '%s': %s",
                        temp_path,
                        clean_ex,
                    )
