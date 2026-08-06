"""
RAG Ingestion Pipeline Subsystem (app/ai/rag/ingestion/pipeline.py).

Đóng vai trò Orchestrator thực thi toàn bộ luồng xử lý ngầm (Background Tasks):
1. Extract Text từ file (.docx / .txt)
2. Chunking ngữ nghĩa với TextChunker
3. Đính kèm siêu dữ liệu RBAC (accessScope, allowedRoles, backendId)
4. Embed qua TEI Embedding Service (Mini-batching 16 chunks/lần)
5. Upsert Vector Store CSDL SQL Server (với autocommit Vector Index handling)
6. Đồng bộ trạng thái Ingest sang RagDocuments & IngestionFiles
7. Cập nhật tiến độ % và trạng thái hoàn thành vào bảng IngestionTasks
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional

from app.ai.rag.ingestion.extractor import FileTextExtractor
from app.ai.rag.text_splitter import TextChunker
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.modules.document.repository import DocumentRepository

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Pipeline xử lý ngầm Ingestion hoàn chỉnh."""

    def __init__(self, repository: DocumentRepository, embedding_service: TeiEmbeddingService):
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
        metadata: Dict[str, Any],
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
        metadata: Dict[str, Any],
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
            logger.info("[PIPELINE] Starting ingestion task=%s for file='%s' (backend_id=%s)...",
                        task_id, file_name, backend_id)

            # 1. Update status = PROCESSING, progress = 10%
            self.repository.update_ingestion_task(task_id, status="PROCESSING", progress_percent=10)

            # 2. Extract Text
            text_content = self.extractor.extract(temp_path, file_name)
            self.repository.update_ingestion_task(task_id, status="PROCESSING", progress_percent=20)

            # 3. Chunking ngữ nghĩa
            chunks = self.chunker.split_text(text_content)
            if not chunks:
                chunks = [f"Nội dung tài liệu {file_name}"]
            self.repository.update_ingestion_task(task_id, status="PROCESSING", progress_percent=30)

            # 4. Đính kèm siêu dữ liệu RBAC vào từng chunk
            access_scope = metadata.get("accessScope", metadata.get("access_scope", "Public"))
            allowed_roles = metadata.get("allowedRoles", metadata.get("allowed_roles", []))
            owner_dept = metadata.get("ownerDepartment") or metadata.get("owner_department")

            chunk_ids = [f"{backend_id}_{i}" for i in range(len(chunks))]
            chunk_metadatas = [
                {
                    "backendId": backend_id,
                    "backend_document_id": int(backend_id) if backend_id.isdigit() else 0,
                    "backend_id": backend_id,
                    "source": file_name,
                    "accessScope": access_scope,
                    "allowedRoles": allowed_roles,
                    "owner_department": owner_dept,
                    "ownerDepartment": owner_dept,
                    "page": i + 1,
                    "category": metadata.get("category"),
                }
                for i in range(len(chunks))
            ]

            # 5. Embed qua TEI Server (Mini-batching) — progress = 50%
            self.repository.update_ingestion_task(task_id, status="PROCESSING", progress_percent=50)
            embeddings = await self.embedding_service.embed_texts(chunks)

            # 6. Upsert vào SQL Server Vector Store — progress = 80%
            self.repository.update_ingestion_task(task_id, status="PROCESSING", progress_percent=80)
            self.repository.upsert_documents(
                ids=chunk_ids,
                documents=chunks,
                metadatas=chunk_metadatas,
                embeddings=embeddings,
            )

            # 7. Cập nhật trạng thái Ingest trên RagDocuments nếu có backend_id
            if backend_id.isdigit() and int(backend_id) > 0:
                self.repository.update_rag_document_status(int(backend_id), "Completed", len(chunks))

            # 8. Ghi đồng bộ log vào bảng IngestionFiles (tương thích DB cũ)
            self.repository.upsert_ingestion_file(
                file_name=file_name,
                file_size=file_size,
                status="completed",
                chunk_count=len(chunks),
            )

            # 9. Hoàn thành task: COMPLETED, progress = 100%
            self.repository.update_ingestion_task(
                task_id,
                status="COMPLETED",
                progress_percent=100,
                chunk_count=len(chunks),
            )
            logger.info("[PIPELINE SUCCESS] Task=%s completed! Ingested %d chunks.", task_id, len(chunks))

        except Exception as ex:
            logger.error("[PIPELINE FAIL] Error during ingestion task=%s: %s", task_id, ex, exc_info=True)
            # Cập nhật RagDocuments status = Failed nếu có backend_id để tránh kẹt Processing
            try:
                if backend_id.isdigit() and int(backend_id) > 0:
                    self.repository.update_rag_document_status(int(backend_id), "Failed", 0, str(ex))
            except Exception:
                logger.warning("[WARN] Could not update RagDocuments status to Failed for doc ID %s", backend_id)

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
                except Exception as clean_ex:
                    logger.warning("[WARN] Failed to delete temp file '%s': %s", temp_path, clean_ex)
