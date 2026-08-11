"""
Repository xử lý CSDL và Phân quyền Truy vấn Vector (Document & RBAC Repository).
Đóng gói Data Access Layer sử dụng SQLAlchemy ORM (SessionLocal) từ app.core.database.

Cơ chế RBAC Filtering trong SQL Vector Search:
- Chỉ trả về các Vector Chunks thuộc tài liệu `Public`
- HOẶC thuộc tài liệu `Restricted` mà `allowedRoles` trùng khớp với `user_roles` của request.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.modules.document.model import RagDocument, RagDocumentRole, IngestionTask

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository quản lý siêu dữ liệu tài liệu RAG và truy vấn Vector SQL Server sử dụng ORM SessionLocal."""

    # --- RAG Documents Metadata ORM CRUD ---

    def create_rag_document(
        self,
        document_name: str,
        file_name: str,
        file_path: str,
        file_size: int,
        category: str | None = None,
        owner_department: str | None = None,
        description: str | None = None,
        tags: str | None = None,
        access_scope: str = "Public",
        effective_date: str | None = None,
        expiration_date: str | None = None,
        uploaded_by: str | None = None,
        tenant_id: int | None = None,
        allowed_roles: list[str] | None = None,
    ) -> int:
        """Tạo bản ghi tài liệu mới kèm khai báo Vai trò (Roles) truy cập bằng ORM."""
        allowed_roles = allowed_roles or []

        db: Session = SessionLocal()
        try:
            doc = RagDocument(
                document_name=document_name,
                file_name=file_name,
                file_path=file_path,
                file_size=file_size,
                category=category,
                owner_department=owner_department,
                description=description,
                tags=tags,
                access_scope=access_scope,
                effective_date=datetime.fromisoformat(effective_date)
                if effective_date
                else None,
                expiration_date=datetime.fromisoformat(expiration_date)
                if expiration_date
                else None,
                uploaded_by=uploaded_by,
                tenant_id=tenant_id,
                ingest_status="Pending",
                creation_time=datetime.utcnow(),
            )
            db.add(doc)
            db.flush()  # Lấy doc.id tự sinh

            if access_scope.lower() == "restricted" and allowed_roles:
                for role in allowed_roles:
                    if role.strip():
                        db.add(
                            RagDocumentRole(
                                rag_document_id=doc.id, role_name=role.strip()
                            )
                        )

            db.commit()
            logger.info(
                "[OK] Created RagDocument ID=%d (ORM), Scope=%s, Roles=%s",
                doc.id,
                access_scope,
                allowed_roles,
            )
            return doc.id
        except Exception as ex:
            db.rollback()
            logger.error(
                "[FAIL] Error creating RagDocument via ORM: %s", ex, exc_info=True
            )
            raise ex
        finally:
            db.close()

    def get_rag_documents_list(self) -> list[dict[str, Any]]:
        """Lấy danh sách tất cả tài liệu RAG kèm danh sách vai trò truy cập bằng ORM."""
        db: Session = SessionLocal()
        try:
            docs = db.query(RagDocument).order_by(RagDocument.id.desc()).all()
            results = []
            for doc in docs:
                roles_list = [r.role_name for r in doc.roles]
                results.append(
                    {
                        "id": doc.id,
                        "document_name": doc.document_name,
                        "file_name": doc.file_name,
                        "file_path": doc.file_path,
                        "file_size": doc.file_size,
                        "category": doc.category,
                        "owner_department": doc.owner_department,
                        "access_scope": doc.access_scope,
                        "ingest_status": doc.ingest_status,
                        "chunk_count": doc.chunk_count,
                        "creation_time": str(doc.creation_time)
                        if doc.creation_time
                        else None,
                        "allowed_roles": roles_list,
                    }
                )
            return results
        finally:
            db.close()

    def get_rag_document(self, doc_id: int) -> dict[str, Any] | None:
        """Lấy chi tiết 1 tài liệu RAG theo ID bằng ORM."""
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if not doc:
                return None
            roles_list = [r.role_name for r in doc.roles]
            return {
                "id": doc.id,
                "document_name": doc.document_name,
                "file_name": doc.file_name,
                "file_path": doc.file_path,
                "file_size": doc.file_size,
                "category": doc.category,
                "owner_department": doc.owner_department,
                "access_scope": doc.access_scope,
                "ingest_status": doc.ingest_status,
                "chunk_count": doc.chunk_count,
                "creation_time": str(doc.creation_time) if doc.creation_time else None,
                "allowed_roles": roles_list,
            }
        finally:
            db.close()

    def get_rag_document_roles(self, doc_id: int) -> list[str]:
        """Lấy danh sách vai trò được truy cập của tài liệu bằng ORM."""
        db: Session = SessionLocal()
        try:
            roles = (
                db.query(RagDocumentRole)
                .filter(RagDocumentRole.rag_document_id == doc_id)
                .all()
            )
            return [r.role_name for r in roles]
        finally:
            db.close()

    def update_rag_document_status(
        self, doc_id: int, status: str, chunk_count: int, error: str | None = None
    ) -> None:
        """Cập nhật trạng thái Ingest từ C# Gateway bằng ORM."""
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.ingest_status = status
                doc.chunk_count = chunk_count
                doc.ingest_error = error
                doc.last_modification_time = datetime.utcnow()
                db.commit()
        except Exception as ex:
            db.rollback()
            logger.error(
                "[FAIL] Error updating RagDocument status ID=%d: %s",
                doc_id,
                ex,
                exc_info=True,
            )
            raise ex
        finally:
            db.close()

    def update_rag_document(
        self,
        doc_id: int,
        document_name: str,
        category: str | None,
        access_scope: str,
        allowed_roles: list[str],
    ) -> None:
        """Cập nhật siêu dữ liệu và danh sách vai trò được phép truy cập bằng ORM."""
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.document_name = document_name
                doc.category = category
                doc.access_scope = access_scope
                doc.last_modification_time = datetime.utcnow()

                # Xóa roles cũ và nạp lại roles mới
                db.query(RagDocumentRole).filter(
                    RagDocumentRole.rag_document_id == doc_id
                ).delete()
                if access_scope.lower() == "restricted" and allowed_roles:
                    for role in allowed_roles:
                        if role.strip():
                            db.add(
                                RagDocumentRole(
                                    rag_document_id=doc_id, role_name=role.strip()
                                )
                            )

                db.commit()
                logger.info(
                    "[OK] Updated RagDocument ID=%d (ORM) with roles=%s",
                    doc_id,
                    allowed_roles,
                )
        except Exception as ex:
            db.rollback()
            logger.error(
                "[FAIL] Error updating RagDocument ID=%d: %s", doc_id, ex, exc_info=True
            )
            raise ex
        finally:
            db.close()

    def delete_rag_document(self, backend_id: int) -> str | None:
        """Xóa tài liệu và các vai trò theo backend_id bằng ORM, trả về FilePath để xóa file vật lý."""
        file_path = None
        file_name = None
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == backend_id).first()
            if doc:
                file_path = doc.file_path
                file_name = doc.file_name
                db.delete(doc)  # Cascade tự xóa RagDocumentRoles
                db.commit()
        except Exception as ex:
            db.rollback()
            logger.error(
                "[FAIL] Error deleting RagDocument ID=%d: %s",
                backend_id,
                ex,
                exc_info=True,
            )
            raise ex
        finally:
            db.close()

        # Xóa các Chunks trong bảng Documents
        self.delete_documents_by_backend_id(backend_id, file_name=file_name)
        return file_path

    def delete_documents_by_backend_id(
        self, backend_id: int, file_name: str | None = None
    ) -> None:
        """
        Xóa các chunk vector thuộc tài liệu có backendId tương ứng hoặc file_name tương ứng.
        Lưu ý: SQL Server 2025 yêu cầu tạm DROP Vector Index trước khi DELETE dòng,
        và CREATE VECTOR INDEX bắt buộc chạy ở chế độ autocommit độc lập.
        """
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                # 1. Tạm drop Vector Index nếu có để tránh lỗi SQL Server 42231 khi DELETE
                try:
                    cursor.execute(
                        "DROP INDEX IF EXISTS idx_documents_embedding ON dbo.Documents;"
                    )
                except Exception as idx_ex:  # noqa: BLE001
                    logger.warning(
                        "[WARN] Exception dropping vector index before DELETE: %s",
                        idx_ex,
                    )

                # 2. Xóa các chunks theo backend_id hoặc source file_name
                if file_name:
                    cursor.execute(
                        """
                        DELETE FROM Documents
                        WHERE JSON_VALUE(metadata, '$.backendId') = ?
                           OR JSON_VALUE(metadata, '$.backend_document_id') = ?
                           OR JSON_VALUE(metadata, '$.backend_id') = ?
                           OR JSON_VALUE(metadata, '$.source') = ?;
                    """,
                        (str(backend_id), str(backend_id), str(backend_id), file_name),
                    )
                else:
                    cursor.execute(
                        """
                        DELETE FROM Documents
                        WHERE JSON_VALUE(metadata, '$.backendId') = ?
                           OR JSON_VALUE(metadata, '$.backend_document_id') = ?
                           OR JSON_VALUE(metadata, '$.backend_id') = ?;
                    """,
                        (str(backend_id), str(backend_id), str(backend_id)),
                    )

            raw_conn.commit()
            logger.info("[OK] Deleted vector chunks for backend_id=%d", backend_id)
        finally:
            raw_conn.close()

        # 3. Tái tạo lại Vector Index bằng kết nối autocommit độc lập (tránh lỗi transaction 574 của SQL Server 2025)
        try:
            conn = pyodbc.connect(settings.SQLSERVER_CONNECTIONSTRING, autocommit=True)
            with conn.cursor() as cursor:
                cursor.execute(
                    "CREATE VECTOR INDEX idx_documents_embedding ON dbo.Documents(embedding) WITH (METRIC = 'cosine');"
                )
            conn.close()
        except Exception as idx_ex:  # noqa: BLE001
            logger.warning(
                "[WARN] Exception recreating vector index after DELETE: %s", idx_ex
            )

    def upsert_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """
        Lưu/cập nhật danh sách vector chunks vào CSDL SQL Server.
        Sử dụng CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024)) để tránh lỗi 529 'ntext to vector conversion' của SQL Server 2025.
        Tạm thời DROP Vector Index trước khi MERGE batch và tái tạo lại sau đó để tránh lỗi SQL Server 42231.
        """
        sql = """
            MERGE Documents AS target
            USING (SELECT ? AS id, ? AS document, ? AS metadata, CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024)) AS embedding) AS source
            ON (target.id = source.id)
            WHEN MATCHED THEN
                UPDATE SET target.document = source.document, target.metadata = source.metadata, target.embedding = source.embedding
            WHEN NOT MATCHED THEN
                INSERT (id, document, metadata, embedding)
                VALUES (source.id, source.document, source.metadata, source.embedding);
        """
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                # 1. Tạm drop Vector Index trước khi batch MERGE
                try:
                    cursor.execute(
                        "DROP INDEX IF EXISTS idx_documents_embedding ON dbo.Documents;"
                    )
                except Exception as idx_ex:  # noqa: BLE001
                    logger.warning(
                        "[WARN] Exception dropping vector index before upsert: %s",
                        idx_ex,
                    )

                # 2. Thực thi MERGE các chunks
                for i in range(len(ids)):
                    embed_json = json.dumps(embeddings[i])
                    meta_json = json.dumps(metadatas[i], ensure_ascii=False)
                    cursor.execute(sql, (ids[i], documents[i], meta_json, embed_json))

            raw_conn.commit()
            logger.info("[OK] Upserted %d vector chunks", len(ids))
        finally:
            raw_conn.close()

    def upsert_ingestion_file(
        self,
        file_name: str,
        file_size: int,
        status: str,
        chunk_count: int,
        error: str | None = None,
    ) -> None:
        """Lưu/cập nhật thông tin file vào bảng IngestionFiles để đồng bộ với thiết kế CSDL của dự án Rag cũ."""
        sql = """
            MERGE IngestionFiles AS target
            USING (SELECT ? AS relative_path) AS source
            ON (target.relative_path = source.relative_path)
            WHEN MATCHED THEN
                UPDATE SET target.status = ?, target.chunk_count = ?, target.updated_at_utc = GETUTCDATE(), target.error = ?
            WHEN NOT MATCHED THEN
                INSERT (relative_path, source, last_write_time_utc, length, fingerprint, status, chunk_count, updated_at_utc, error)
                VALUES (?, ?, GETUTCDATE(), ?, ?, ?, ?, GETUTCDATE(), ?);
        """
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        file_name,
                        status,
                        chunk_count,
                        error,
                        file_name,
                        file_name,
                        file_size,
                        file_name,
                        status,
                        chunk_count,
                        error,
                    ),
                )
            raw_conn.commit()
            logger.info("[OK] Logged IngestionFiles record for '%s'", file_name)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[WARN] Failed to log IngestionFiles record: %s", ex)
        finally:
            raw_conn.close()

    # --- INGESTION TASKS ORM CRUD ---

    def create_ingestion_task(self, task_id: str, file_name: str, backend_document_id: Optional[int] = None) -> None:
        """Tạo bản ghi theo dõi tiến độ Ingestion ngầm với status = PENDING."""
        db: Session = SessionLocal()
        try:
            task = IngestionTask(
                task_id=task_id,
                file_name=file_name,
                backend_document_id=backend_document_id,
                status="PENDING",
                progress_percent=0,
                chunk_count=0,
                created_at=datetime.utcnow(),
            )
            db.add(task)
            db.commit()
            logger.info("[OK] Created IngestionTask task_id='%s' for file='%s'", task_id, file_name)
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error creating IngestionTask task_id='%s': %s", task_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    def get_ingestion_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin tiến độ IngestionTask theo task_id UUID."""
        db: Session = SessionLocal()
        try:
            task = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "backend_document_id": task.backend_document_id,
                "file_name": task.file_name,
                "status": task.status,
                "progress_percent": task.progress_percent,
                "chunk_count": task.chunk_count,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            }
        finally:
            db.close()

    def update_ingestion_task(
        self,
        task_id: str,
        status: str,
        progress_percent: int = 0,
        chunk_count: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Cập nhật trạng thái, % tiến độ và lỗi của IngestionTask."""
        db: Session = SessionLocal()
        try:
            task = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if task:
                task.status = status
                if progress_percent > 0:
                    task.progress_percent = progress_percent
                if chunk_count > 0:
                    task.chunk_count = chunk_count
                if error_message is not None:
                    task.error_message = error_message
                task.updated_at = datetime.utcnow()
                db.commit()
                logger.debug("[OK] Updated IngestionTask task_id='%s' status='%s' (%d%%)", task_id, status, progress_percent)
        except Exception as ex:
            db.rollback()
            logger.error("[FAIL] Error updating IngestionTask task_id='%s': %s", task_id, ex, exc_info=True)
            raise ex
        finally:
            db.close()

    # --- VECTOR SEARCH CÓ PHÂN QUYỀN RBAC ---


    def search_vector_chunks(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        content_kind: str | None = None,
        user_roles: str | None = None,
        user_department: str | None = None,
    ) -> dict[str, Any]:
        """
        Tìm kiếm Vector Cosine kết hợp lọc phân quyền người dùng (User Roles RBAC) và Phòng ban (Department RBAC).

        Luật Phân Quyền SQL:
        - Chunk hợp lệ nếu `accessScope` = 'Public' (hoặc NULL)
        - HOẶC `accessScope` = 'Restricted' VÀ user_roles có chứa 'admin'
        - HOẶC `accessScope` = 'Restricted' VÀ `user_roles` khớp với mảng `allowedRoles` lưu trong metadata.
        - VÀ nếu tài liệu chỉ định Phòng ban sở hữu (owner_department), chỉ user thuộc phòng ban đó (hoặc Admin) mới xem được.
        """
        top_k = max(1, min(top_k, settings.SEARCH_TOP_K_MAX))
        candidate_count = max(top_k, settings.SEARCH_VECTOR_CANDIDATE_COUNT)
        rrf_constant = (
            settings.SEARCH_RRF_CONSTANT if settings.SEARCH_RRF_CONSTANT > 0 else 60
        )
        query_embedding_json = json.dumps(query_embedding)

        match = re.search(r"\b\d{6,}\b", query)
        exact_keyword = match.group(0) if match else ""

        sql = """
            WITH FilteredDocuments AS (
                SELECT id, document, metadata, embedding
                FROM Documents
                WHERE (? IS NULL OR JSON_VALUE(metadata, '$.content_kind') = ?)
                  AND (
                      JSON_VALUE(metadata, '$.accessScope') IS NULL 
                      OR JSON_VALUE(metadata, '$.accessScope') = 'Public'
                      OR (
                          JSON_VALUE(metadata, '$.accessScope') = 'Restricted'
                          AND ? IS NOT NULL
                          AND (
                              CHARINDEX('admin', LOWER(?)) > 0
                              OR EXISTS (
                                  SELECT 1 
                                  FROM OPENJSON(metadata, '$.allowedRoles') WITH (role NVARCHAR(100) '$')
                                  WHERE role IN (SELECT value FROM STRING_SPLIT(?, ','))
                              )
                          )
                      )
                  )
                  AND (
                      ? IS NULL OR ? = ''
                      OR CHARINDEX('admin', LOWER(?)) > 0
                      OR (
                          ISNULL(JSON_VALUE(metadata, '$.owner_department'), '') = ''
                          AND ISNULL(JSON_VALUE(metadata, '$.ownerDepartment'), '') = ''
                      )
                      OR LOWER(JSON_VALUE(metadata, '$.owner_department')) = LOWER(?)
                      OR LOWER(JSON_VALUE(metadata, '$.ownerDepartment')) = LOWER(?)
                  )
            ),
            VectorBase AS (
                SELECT
                    id, document, metadata,
                    VECTOR_DISTANCE('cosine', embedding, CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) AS distance
                FROM FilteredDocuments
            ),
            VectorSearch AS (
                SELECT TOP (?)
                    id, document, metadata, distance,
                    ROW_NUMBER() OVER (ORDER BY distance ASC) AS vector_rank
                FROM VectorBase
                ORDER BY distance ASC
            ),
            ExactMatchSearch AS (
                SELECT id, 10000 AS exact_score
                FROM FilteredDocuments
                WHERE ? <> '' AND document LIKE '%' + ? + '%'
            ),
            CandidateIds AS (
                SELECT id FROM VectorSearch
                UNION
                SELECT id FROM ExactMatchSearch
            ),
            RankedScores AS (
                SELECT c.id, d.document, d.metadata, v.distance, v.vector_rank, e.exact_score
                FROM CandidateIds c
                INNER JOIN FilteredDocuments d ON d.id = c.id
                LEFT JOIN VectorSearch v ON v.id = c.id
                LEFT JOIN ExactMatchSearch e ON e.id = c.id
            )
            SELECT TOP (?)
                id, document, metadata, distance,
                (1.0 / (? + ISNULL(vector_rank, 9999))) + ISNULL(exact_score, 0) AS RRF_Score
            FROM RankedScores
            ORDER BY RRF_Score DESC;
        """

        ids, documents, metadatas, distances, citations = [], [], [], [], []

        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                params = (
                    content_kind,
                    content_kind,
                    user_roles,
                    user_roles,
                    user_roles,
                    user_department,
                    user_department,
                    user_roles or "",
                    user_department,
                    user_department,
                    query_embedding_json,
                    candidate_count,
                    exact_keyword,
                    exact_keyword,
                    top_k,
                    rrf_constant,
                )
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    doc_id, doc_text, meta_json, dist, score = row
                    meta = json.loads(meta_json) if meta_json else {}
                    dist_val = float(dist) if dist is not None else 9999.0
                    score_val = float(score) if score is not None else 0.0

                    ids.append(doc_id)
                    documents.append(doc_text)
                    metadatas.append(meta)
                    distances.append(dist_val)
                    citations.append(
                        {
                            "source": meta.get("source"),
                            "page": meta.get("page") or meta.get("slide"),
                            "chunk_id": doc_id,
                            "score": score_val,
                        }
                    )
        finally:
            raw_conn.close()

        return {
            "ids": [ids],
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": [distances],
            "citations": [citations],
        }
