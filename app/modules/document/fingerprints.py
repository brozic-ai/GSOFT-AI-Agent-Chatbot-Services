"""Transactional fingerprint, retry and ingestion admission operations.

Only the internal gateway may supply tenant/identity headers. Browser hash values
are hints; both the gateway and ingestion endpoint hash the actual bytes.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import case

from app.core.database import SessionLocal
from app.modules.document.model import (
    IngestionTask,
    RagDocument,
    RagDocumentFingerprint,
)


def tenant_scope(tenant_id):
    return "host" if tenant_id is None else f"tenant:{tenant_id}"


def parse_scope(value):
    if value == "host":
        return None
    if (
        value
        and value.startswith("tenant:")
        and value[7:].isdigit()
        and int(value[7:]) > 0
    ):
        return int(value[7:])
    raise ValueError("Invalid tenant scope")


def can_read(doc, roles, department=None):
    user_roles = {r.strip().casefold() for r in (roles or "").split(",") if r.strip()}
    if "admin" in user_roles:
        return True
    allowed = {r.casefold() for r in doc.get("allowed_roles", [])}
    if doc.get(
        "access_scope", "Public"
    ).casefold() != "public" and not allowed.intersection(user_roles):
        return False
    departments = {
        d.strip().casefold()
        for d in (doc.get("owner_department") or "").split(",")
        if d.strip()
    }
    return not departments or (department or "").casefold() in departments


class DocumentConflict(Exception):
    def __init__(self, code, document_id=None):
        self.code = code
        self.document_id = document_id
        super().__init__(code)


def duplicate_code(status):
    return {
        "failed": "RETRY_AVAILABLE",
        "pending": "IN_PROGRESS",
        "processing": "IN_PROGRESS",
    }.get((status or "").lower(), "DUPLICATE")


class FingerprintOperations:
    @staticmethod
    def _locked(query):
        # HOLDLOCK covers the transaction, including the vector replacement commit.
        return query.with_hint(
            RagDocument, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql"
        )

    def find_fingerprint(self, scope, sha256):
        with SessionLocal() as db:
            row = db.get(RagDocumentFingerprint, (scope, sha256))
            return row.document_id if row else None

    def check_fingerprints(self, items, scope, roles="", department=None):
        hashes = [item.sha256 for item in items]
        with SessionLocal() as db:
            rows = (
                db.query(RagDocumentFingerprint)
                .filter(
                    RagDocumentFingerprint.tenant_scope == scope,
                    RagDocumentFingerprint.file_sha256.in_(hashes),
                )
                .all()
            )
            existing = {row.file_sha256: row.document_id for row in rows}
        results = []
        first = {}
        for item in items:
            result = {"fileId": item.fileId, "status": "NEW"}
            doc_id = existing.get(item.sha256)
            if doc_id:
                doc = self.get_rag_document(doc_id)
                visible = doc and can_read(doc, roles, department)
                result["status"] = (
                    duplicate_code(doc.get("ingest_status")) if visible else "DUPLICATE"
                )
                if visible:
                    result["document"] = {
                        "id": doc_id,
                        "documentName": doc["document_name"],
                        "ingestStatus": doc["ingest_status"],
                        "creationTime": doc["creation_time"],
                    }
                    result["canRetry"] = result["status"] == "RETRY_AVAILABLE"
            elif item.sha256 in first:
                result.update(status="BATCH_DUPLICATE", duplicateOf=first[item.sha256])
            first.setdefault(item.sha256, item.fileId)
            results.append(result)
        return results

    def begin_retry(self, doc_id, scope, expected_hash):
        with SessionLocal() as db:
            attempt = str(uuid.uuid4())
            changed = (
                db.query(RagDocument)
                .filter(
                    RagDocument.id == doc_id,
                    RagDocument.tenant_id == parse_scope(scope),
                    RagDocument.file_sha256 == expected_hash,
                    RagDocument.ingest_status == "Failed",
                )
                .update(
                    {
                        RagDocument.ingest_status: "Pending",
                        RagDocument.ingest_error: None,
                        RagDocument.current_ingestion_attempt_id: attempt,
                        RagDocument.last_modification_time: datetime.now(UTC),
                    },
                    synchronize_session=False,
                )
            )
            if changed != 1:
                raise DocumentConflict("RETRY_NOT_ALLOWED", doc_id)
            db.commit()
            return attempt

    def accept_ingestion(self, doc_id, attempt, sha256, scope, file_name):
        with SessionLocal() as db:
            doc = (
                self._locked(db.query(RagDocument))
                .filter(RagDocument.id == doc_id)
                .first()
            )
            if not doc or tenant_scope(doc.tenant_id) != scope:
                raise DocumentConflict("DOCUMENT_NOT_FOUND")
            if doc.current_ingestion_attempt_id != attempt or doc.file_sha256 != sha256:
                raise DocumentConflict("ATTEMPT_OR_HASH_MISMATCH")
            task = (
                db.query(IngestionTask)
                .filter_by(backend_document_id=doc_id, attempt_id=attempt)
                .first()
            )
            if task:
                return task.task_id, False
            if doc.ingest_status != "Pending":
                raise DocumentConflict("IN_PROGRESS", doc_id)
            task_id = str(uuid.uuid4())
            db.add(
                IngestionTask(
                    task_id=task_id,
                    backend_document_id=doc_id,
                    attempt_id=attempt,
                    file_name=file_name,
                    status="PENDING",
                    created_at=datetime.now(UTC),
                )
            )
            doc.ingest_status = "Processing"
            db.commit()
            return task_id, True

    def get_attempt_task(self, doc_id, attempt):
        with SessionLocal() as db:
            task = (
                db.query(IngestionTask)
                .filter_by(backend_document_id=doc_id, attempt_id=attempt)
                .first()
            )
            return self.get_ingestion_task(task.task_id) if task else None

    def backfill_fingerprint(self, doc_id, sha256, scope):
        with SessionLocal() as db:
            doc = (
                self._locked(db.query(RagDocument))
                .filter(
                    RagDocument.id == doc_id,
                    RagDocument.tenant_id == parse_scope(scope),
                )
                .first()
            )
            if not doc:
                raise DocumentConflict("DOCUMENT_NOT_FOUND")
            if doc.file_sha256 and doc.file_sha256 != sha256:
                raise DocumentConflict("SOURCE_CHANGED", doc_id)
            doc.file_sha256 = sha256
            db.flush()
            candidates = db.query(RagDocument).filter(
                RagDocument.tenant_id == doc.tenant_id,
                RagDocument.file_sha256 == sha256,
            )
            rank = case(
                (RagDocument.ingest_status == "Completed", 0),
                (RagDocument.ingest_status.in_(["Pending", "Processing"]), 1),
                else_=2,
            )
            winner = candidates.order_by(rank, RagDocument.id).first()
            row = db.get(RagDocumentFingerprint, (scope, sha256))
            if row:
                row.document_id = winner.id
            else:
                db.add(
                    RagDocumentFingerprint(
                        tenant_scope=scope, file_sha256=sha256, document_id=winner.id
                    )
                )
            count = candidates.count()
            db.commit()
            return {
                "documentId": doc_id,
                "canonicalDocumentId": winner.id,
                "copies": count,
            }

    def fingerprint_candidates(self, scope, cursor, limit=100):
        with SessionLocal() as db:
            return [
                {
                    "id": d.id,
                    "file_path": d.file_path,
                    "file_name": d.file_name,
                    "file_sha256": d.file_sha256,
                }
                for d in db.query(RagDocument)
                .filter(
                    RagDocument.tenant_id == parse_scope(scope), RagDocument.id > cursor
                )
                .order_by(RagDocument.id)
                .limit(limit)
                .all()
            ]

    def fingerprint_coverage(self, scope):
        with SessionLocal() as db:
            docs = db.query(RagDocument).filter(
                RagDocument.tenant_id == parse_scope(scope)
            )
            total = docs.count()
            hashed = docs.filter(RagDocument.file_sha256.isnot(None)).count()
            return {
                "totalDocuments": total,
                "hashedDocuments": hashed,
                "unhashedDocuments": total - hashed,
            }
