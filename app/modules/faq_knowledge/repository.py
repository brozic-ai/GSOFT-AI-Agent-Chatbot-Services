"""
FAQ Knowledge Base Repository: Tầng truy xuất dữ liệu từ Database.
Tách biệt hoàn toàn logic tương tác DB ra khỏi Service và API.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.faq_knowledge.model import FaqKnowledge

logger = logging.getLogger(__name__)


def _normalize_question(question: str) -> str:
    """Chuẩn hóa chuỗi câu hỏi: lowercase, strip khoảng trắng thừa."""
    return " ".join(question.strip().lower().split())


class FaqRepository:
    """Repository xử lý các thao tác CRUD với bảng FAQ_Knowledge_Base."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------------
    def create(
        self,
        question: str,
        answer: str,
        category: str | None = None,
        metadata_json: str | None = None,
    ) -> FaqKnowledge:
        """Tạo mới 1 bản ghi FAQ. Caller chịu trách nhiệm commit."""
        normalized = _normalize_question(question)
        faq = FaqKnowledge(
            question=question.strip(),
            question_normalized=normalized,
            answer=answer.strip(),
            category=category,
            metadata_json=metadata_json,
        )
        self.db.add(faq)
        return faq

    # -------------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------------
    def get_by_id(self, faq_id: int) -> FaqKnowledge | None:
        """Lấy 1 FAQ theo ID."""
        return self.db.get(FaqKnowledge, faq_id)

    def get_all(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> tuple[list[FaqKnowledge], int]:
        """Lấy danh sách FAQ có phân trang, hỗ trợ lọc theo category.
        
        Returns:
            Tuple (danh sách FAQ, tổng số bản ghi).
        """
        stmt = select(FaqKnowledge)
        count_stmt = select(func.count()).select_from(FaqKnowledge)

        if category:
            stmt = stmt.where(FaqKnowledge.category == category)
            count_stmt = count_stmt.where(FaqKnowledge.category == category)

        total = self.db.execute(count_stmt).scalar_one()

        stmt = (
            stmt.order_by(FaqKnowledge.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(self.db.execute(stmt).scalars())
        return items, total

    def get_by_normalized_question(self, question: str) -> FaqKnowledge | None:
        """Kiểm tra câu hỏi đã tồn tại (sau chuẩn hóa) để tránh trùng lặp."""
        normalized = _normalize_question(question)
        stmt = select(FaqKnowledge).where(
            FaqKnowledge.question_normalized == normalized
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def exists_normalized(self, question: str) -> bool:
        """Trả về True nếu câu hỏi (sau chuẩn hóa) đã tồn tại trong DB."""
        return self.get_by_normalized_question(question) is not None

    # -------------------------------------------------------------------------
    # UPDATE
    # -------------------------------------------------------------------------
    def update(
        self,
        faq: FaqKnowledge,
        question: str | None = None,
        answer: str | None = None,
        category: str | None = None,
        metadata_json: str | None = None,
    ) -> FaqKnowledge:
        """Cập nhật thông tin FAQ. Caller chịu trách nhiệm commit."""
        if question is not None:
            faq.question = question.strip()
            faq.question_normalized = _normalize_question(question)
        if answer is not None:
            faq.answer = answer.strip()
        if category is not None:
            faq.category = category
        if metadata_json is not None:
            faq.metadata_json = metadata_json
        return faq

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------
    def delete(self, faq: FaqKnowledge) -> None:
        """Xóa 1 FAQ khỏi DB. Caller chịu trách nhiệm commit."""
        self.db.delete(faq)

    # -------------------------------------------------------------------------
    # VECTOR STORE — FaqVectors Operations (dbo.FaqVectors)
    # -------------------------------------------------------------------------
    def upsert_faq_vector(
        self,
        faq_id: int,
        question: str,
        answer: str,
        embedding: list[float],
    ) -> None:
        """
        Lưu / cập nhật 1 vector của câu hỏi FAQ vào bảng dbo.FaqVectors.
        Sử dụng MERGE + CAST VECTOR(1024) giống pattern của DocumentRepository.
        Dùng raw connection để tránh lỗi 529 của SQL Server khi cast ntext → VECTOR.
        """
        import json

        from app.core.database import engine

        sql = """
            MERGE FaqVectors AS target
            USING (
                SELECT ? AS faq_id,
                       ? AS question,
                       ? AS answer,
                       CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024)) AS embedding
            ) AS source
            ON target.faq_id = source.faq_id
            WHEN MATCHED THEN
                UPDATE SET
                    target.question  = source.question,
                    target.answer    = source.answer,
                    target.embedding = source.embedding
            WHEN NOT MATCHED THEN
                INSERT (faq_id, question, answer, embedding)
                VALUES (source.faq_id, source.question, source.answer, source.embedding);
        """
        embed_json = json.dumps(embedding)
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute(sql, (faq_id, question, answer, embed_json))
            raw_conn.commit()
        except Exception as ex:
            raw_conn.rollback()
            logger.error("[FAQ VECTOR] upsert_faq_vector faq_id=%d error: %s", faq_id, ex)
            raise
        finally:
            raw_conn.close()

    def bulk_upsert_faq_vectors(
        self,
        items: list[tuple[int, str, str, list[float]]],
    ) -> None:
        """
        Upsert hàng loạt vector FAQ vào bảng FaqVectors.

        Args:
            items: List[Tuple[faq_id, question, answer, embedding_list]].
        """
        import json

        from app.core.database import engine

        if not items:
            return

        sql = """
            MERGE FaqVectors AS target
            USING (
                SELECT ? AS faq_id,
                       ? AS question,
                       ? AS answer,
                       CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024)) AS embedding
            ) AS source
            ON target.faq_id = source.faq_id
            WHEN MATCHED THEN
                UPDATE SET
                    target.question  = source.question,
                    target.answer    = source.answer,
                    target.embedding = source.embedding
            WHEN NOT MATCHED THEN
                INSERT (faq_id, question, answer, embedding)
                VALUES (source.faq_id, source.question, source.answer, source.embedding);
        """
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                # Tạm drop Vector Index (tương tự DocumentRepository) để tránh lỗi SQL Server 42231
                try:
                    cursor.execute(
                        "DROP INDEX IF EXISTS idx_faqvectors_embedding ON dbo.FaqVectors;"
                    )
                except Exception:  # noqa: BLE001
                    pass
                for faq_id, question, answer, embedding in items:
                    embed_json = json.dumps(embedding)
                    cursor.execute(sql, (faq_id, question, answer, embed_json))
            raw_conn.commit()
            logger.info("[FAQ VECTOR] bulk_upsert_faq_vectors: %d items upserted.", len(items))
        except Exception as ex:
            raw_conn.rollback()
            logger.error("[FAQ VECTOR] bulk_upsert_faq_vectors error: %s", ex)
            raise
        finally:
            # Tái tạo lại vector index sau khi batch xong
            try:
                raw_conn2 = engine.raw_connection()
                with raw_conn2.cursor() as cur2:
                    cur2.execute(
                        "IF NOT EXISTS ("
                        "SELECT 1 FROM sys.indexes "
                        "WHERE name='idx_faqvectors_embedding' "
                        "AND object_id = OBJECT_ID('dbo.FaqVectors')"
                        ") "
                        "CREATE VECTOR INDEX idx_faqvectors_embedding "
                        "ON dbo.FaqVectors(embedding);"
                    )
                raw_conn2.commit()
                raw_conn2.close()
            except Exception:  # noqa: BLE001
                pass

    def delete_faq_vector(self, faq_id: int) -> None:
        """Xóa vector của câu hỏi FAQ khỏi bảng FaqVectors theo faq_id."""
        from app.core.database import engine

        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute("DELETE FROM FaqVectors WHERE faq_id = ?", (faq_id,))
            raw_conn.commit()
            logger.info("[FAQ VECTOR] delete_faq_vector faq_id=%d deleted.", faq_id)
        except Exception as ex:
            raw_conn.rollback()
            logger.error("[FAQ VECTOR] delete_faq_vector faq_id=%d error: %s", faq_id, ex)
            raise
        finally:
            raw_conn.close()

    def get_faqs_without_vector(self, limit: int = 500) -> list[FaqKnowledge]:
        """
        Lấy danh sách FAQ chưa có bản ghi trong FaqVectors.
        Dùng để phục vụ tính năng sync hàng loạt (POST /sync-vectors).
        """
        from app.core.database import engine

        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT TOP (?) kb.Id FROM FAQ_Knowledge_Base kb "
                    "WHERE NOT EXISTS (SELECT 1 FROM FaqVectors fv WHERE fv.faq_id = kb.Id) "
                    "ORDER BY kb.Id ASC",
                    (limit,),
                )
                rows = cursor.fetchall()
            ids = [row[0] for row in rows]
        finally:
            raw_conn.close()

        if not ids:
            return []
        stmt = select(FaqKnowledge).where(FaqKnowledge.id.in_(ids))
        return list(self.db.execute(stmt).scalars())

    def search_faq_hybrid(
        self,
        query_embedding: list[float],
        query: str,
        top_k: int = 5,
        rrf_min_score: float = 0.01,
    ) -> list[dict]:
        """
        Hybrid Search trên bảng dbo.FaqVectors bằng thuật toán RRF có trọng số.

        Kết hợp:
        - Vector Search: VECTOR_DISTANCE('cosine') trên cột embedding VECTOR(1024).
        - Full-Text Search: CONTAINSTABLE trên cột question + answer (LANGUAGE 0).
        RRF Score = α * 1/(k + vector_rank) + β * 1/(k + fts_rank_pos)
        Lọc kết quả có RRF Score < rrf_min_score (Fallback Threshold).

        Args:
            query_embedding: Vector 1024 chiều của câu truy vấn.
            query: Câu truy vấn dạng text (dùng cho CONTAINSTABLE).
            top_k: Số kết quả trả về tối đa.
            rrf_min_score: Ngưỡng điểm tối thiểu. Kết quả dưới ngưỡng bị lọc bỏ (Fallback).

        Returns:
            Danh sách dict {'faq_id', 'question', 'answer', 'rrf_score'} đã sắp xếp.
        """
        import json

        from app.core.config import settings
        from app.core.database import engine

        rrf_k = settings.SEARCH_RRF_CONSTANT if settings.SEARCH_RRF_CONSTANT > 0 else 60
        vector_weight = getattr(settings, "RRF_VECTOR_WEIGHT", 0.6)
        fts_weight = getattr(settings, "RRF_FTS_WEIGHT", 0.4)
        fts_enabled = getattr(settings, "FTS_ENABLED", True)
        fts_max_candidates = getattr(settings, "FTS_MAX_CANDIDATES", 200)
        candidate_count = max(top_k * 4, 50)

        query_embedding_json = json.dumps(query_embedding)

        # Xây dựng FTS query string (trích từ _build_fts_query của DocumentRepository nếu có)
        fts_query_str = self._build_faq_fts_query(query) if fts_enabled else ""
        use_fts = fts_enabled and bool(fts_query_str)

        if use_fts:
            sql = f"""
                WITH
                VectorSearch AS (
                    SELECT TOP (?)
                        faq_id, question, answer,
                        VECTOR_DISTANCE('cosine', embedding,
                            CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) AS distance,
                        ROW_NUMBER() OVER (
                            ORDER BY VECTOR_DISTANCE('cosine', embedding,
                                CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) ASC
                        ) AS vector_rank
                    FROM FaqVectors
                ),
                FtsSearch AS (
                    SELECT fv.faq_id, fts.[RANK] AS fts_score
                    FROM FaqVectors fv
                    INNER JOIN CONTAINSTABLE(dbo.FaqVectors, (question, answer), ?, LANGUAGE 0, ?) AS fts
                        ON fv.faq_id = fts.[KEY]
                ),
                FtsRanked AS (
                    SELECT faq_id, fts_score,
                        ROW_NUMBER() OVER (ORDER BY fts_score DESC) AS fts_rank_pos
                    FROM FtsSearch
                ),
                CandidateIds AS (
                    SELECT faq_id FROM VectorSearch
                    UNION
                    SELECT faq_id FROM FtsRanked
                ),
                RankedScores AS (
                    SELECT c.faq_id, fv.question, fv.answer, v.vector_rank, f.fts_rank_pos
                    FROM CandidateIds c
                    INNER JOIN FaqVectors fv ON fv.faq_id = c.faq_id
                    LEFT JOIN VectorSearch v ON v.faq_id = c.faq_id
                    LEFT JOIN FtsRanked f ON f.faq_id = c.faq_id
                )
                SELECT TOP (?)
                    faq_id, question, answer,
                    (
                        {vector_weight} * (1.0 / (? + ISNULL(vector_rank, 9999)))
                      + {fts_weight}    * (1.0 / (? + ISNULL(fts_rank_pos, 9999)))
                    ) AS rrf_score
                FROM RankedScores
                ORDER BY rrf_score DESC;
            """
            params = (
                candidate_count,
                query_embedding_json, query_embedding_json,
                fts_query_str, fts_max_candidates,
                top_k,
                rrf_k, rrf_k,
            )
        else:
            # Vector-only search khi FTS disabled hoặc query không có từ khóa hợp lệ
            sql = f"""
                SELECT TOP (?)
                    faq_id, question, answer,
                    {vector_weight} * (1.0 / (? + ROW_NUMBER() OVER (
                        ORDER BY VECTOR_DISTANCE('cosine', embedding,
                            CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) ASC
                    ))) AS rrf_score
                FROM FaqVectors
                ORDER BY VECTOR_DISTANCE('cosine', embedding,
                    CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) ASC;
            """
            params = (top_k, rrf_k, query_embedding_json, query_embedding_json)

        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        finally:
            raw_conn.close()

        results = []
        for row in rows:
            faq_id, question, answer, rrf_score = row[0], row[1], row[2], float(row[3])
            if rrf_score < rrf_min_score:
                logger.info(
                    "[FAQ SEARCH] Bỏ qua faq_id=%d vì RRF score=%.5f < threshold=%.5f",
                    faq_id, rrf_score, rrf_min_score,
                )
                continue
            results.append({
                "faq_id": faq_id,
                "question": question,
                "answer": answer,
                "rrf_score": rrf_score,
            })
        logger.info(
            "[FAQ SEARCH] Hybrid search trả về %d kết quả (sau filter ngưỡng %.5f).",
            len(results), rrf_min_score,
        )
        return results

    def _build_faq_fts_query(self, query: str) -> str:
        """
        Xây dựng query string phù hợp cho CONTAINSTABLE từ câu truy vấn tự nhiên.
        Nối các từ hợp lệ (≥2 ký tự) bằng toán tử OR để tìm kiếm toàn văn linh hoạt.
        """
        import re
        tokens = re.findall(r"\w+", query.lower())
        stop_words = {"và", "hoặc", "của", "cho", "với", "về", "là", "có", "không", "the", "and", "or", "a"}
        valid_tokens = [t for t in tokens if len(t) >= 2 and t not in stop_words]
        if not valid_tokens:
            return ""
        return " OR ".join(f'"{t}"' for t in valid_tokens[:10])


