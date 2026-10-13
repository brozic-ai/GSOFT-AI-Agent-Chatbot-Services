"""Behavior tests, including opt-in concurrency on SQL Server in a disposable schema.

BV_RUN_SQLSERVER_TESTS=1 python -m unittest discover -s tests -p test_document_fingerprints.py
The existing dbo tables and document files are never changed.
"""

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.modules.document import fingerprints, repository
from app.modules.document.api.v1.schemas import DuplicateFileRequest
from app.modules.document.fingerprints import DocumentConflict, can_read, tenant_scope
from app.modules.document.model import (
    IngestionTask,
    RagDocument,
    RagDocumentFingerprint,
    RagDocumentRole,
)

TABLES = [
    RagDocument.__table__,
    RagDocumentRole.__table__,
    RagDocumentFingerprint.__table__,
    IngestionTask.__table__,
]


class FingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql_server = os.getenv("BV_RUN_SQLSERVER_TESTS") == "1"
        cls.schema = None
        if cls.sql_server:
            cls.original_engine = repository.engine
            cls.schema = "test_fingerprint_" + uuid.uuid4().hex[:12]
            with cls.original_engine.begin() as connection:
                connection.execute(text(f"CREATE SCHEMA [{cls.schema}]"))
            cls.engine = cls.original_engine.execution_options(
                schema_translate_map={None: cls.schema}
            )
        else:
            cls.engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        RagDocument.metadata.create_all(cls.engine, tables=TABLES)
        cls.session = sessionmaker(bind=cls.engine)
        cls.patches = [
            patch.object(repository, "SessionLocal", cls.session),
            patch.object(fingerprints, "SessionLocal", cls.session),
        ]
        for p in cls.patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        RagDocument.metadata.drop_all(cls.engine, tables=TABLES)
        if cls.schema:
            with cls.original_engine.begin() as connection:
                connection.execute(text(f"DROP SCHEMA [{cls.schema}]"))
        else:
            cls.engine.dispose()

    def setUp(self):
        with self.session() as db:
            for model in (
                IngestionTask,
                RagDocumentRole,
                RagDocumentFingerprint,
                RagDocument,
            ):
                db.query(model).delete()
            db.commit()
        self.repo = repository.DocumentRepository()
        self.hash = hashlib.sha256(b"document contents").hexdigest()

    def create(self, name="original.pdf", digest=None, tenant=None, **kwargs):
        return self.repo.create_rag_document(
            document_name=name,
            file_name=name,
            file_path="uploads/rag/source.pdf",
            file_size=17,
            file_sha256=digest or self.hash,
            tenant_id=tenant,
            **kwargs,
        )

    def request(self, identity, digest=None):
        return DuplicateFileRequest(
            fileId=identity, sha256=digest or self.hash, fileSize=17
        )

    def test_renamed_duplicate_and_same_name_different_bytes(self):
        doc = self.create()
        with self.assertRaises(DocumentConflict) as conflict:
            self.create("renamed.pdf")
        self.assertEqual(conflict.exception.document_id, doc)
        other = self.create(digest=hashlib.sha256(b"different content").hexdigest())
        self.assertNotEqual(other, doc)
        with self.session() as db:
            self.assertEqual(db.query(RagDocument).count(), 2)

    def test_host_and_tenants_are_independent(self):
        self.create()
        first, second = self.create(tenant=1), self.create(tenant=2)
        self.assertNotEqual(first, second)
        self.assertEqual(tenant_scope(None), "host")
        self.assertEqual(tenant_scope(1), "tenant:1")

    def test_batch_and_restricted_metadata_redaction(self):
        self.assertEqual(
            self.repo.check_fingerprints(
                [self.request("a"), self.request("b")], "host"
            )[1],
            {"fileId": "b", "status": "BATCH_DUPLICATE", "duplicateOf": "a"},
        )
        doc = self.create(access_scope="Restricted", allowed_roles=["Finance"])
        hidden = self.repo.check_fingerprints(
            [self.request("other-name")], "host", "Staff"
        )[0]
        self.assertEqual(hidden, {"fileId": "other-name", "status": "DUPLICATE"})
        visible = self.repo.check_fingerprints([self.request("a")], "host", "Finance")[
            0
        ]
        self.assertEqual(visible["document"]["id"], doc)
        self.assertNotIn("file_path", visible["document"])

    def test_one_task_per_attempt_and_failed_only_retry(self):
        doc = self.create(access_scope="Restricted", allowed_roles=["Finance"])
        attempt = self.repo.get_rag_document(doc)["current_ingestion_attempt_id"]
        first, admitted = self.repo.accept_ingestion(
            doc, attempt, self.hash, "host", "a.pdf"
        )
        self.assertTrue(admitted)
        repeated, admitted = self.repo.accept_ingestion(
            doc, attempt, self.hash, "host", "a.pdf"
        )
        self.assertFalse(admitted)
        self.assertEqual(repeated, first)
        with self.assertRaises(DocumentConflict):
            self.repo.begin_retry(doc, "host", self.hash)
        self.repo.update_rag_document_status(doc, "Failed", 0, "OCR failed", attempt)
        retry = self.repo.begin_retry(doc, "host", self.hash)
        self.assertNotEqual(retry, attempt)
        with self.assertRaises(DocumentConflict):
            self.repo.update_rag_document_status(
                doc, "Completed", 20, attempt_id=attempt
            )
        self.assertEqual(self.repo.get_rag_document_roles(doc), ["Finance"])
        with self.assertRaises(DocumentConflict):
            self.repo.accept_ingestion(doc, retry, "0" * 64, "host", "a.pdf")
        with self.assertRaises(DocumentConflict):
            self.repo.accept_ingestion(doc, retry, self.hash, "tenant:1", "a.pdf")
        self.repo.accept_ingestion(doc, retry, self.hash, "host", "a.pdf")
        self.repo.update_rag_document_status(doc, "Completed", 3, attempt_id=retry)
        with self.assertRaises(DocumentConflict):
            self.repo.begin_retry(doc, "host", self.hash)

    def test_legacy_backfill_is_repeatable_and_reassigns_canonical(self):
        with self.session() as db:
            for name, status in [
                ("old-failed.pdf", "Failed"),
                ("old-success.pdf", "Completed"),
            ]:
                db.add(
                    RagDocument(
                        document_name=name,
                        file_name=name,
                        file_path="legacy/shared.pdf",
                        file_size=17,
                        ingest_status=status,
                    )
                )
            db.commit()
            docs = db.query(RagDocument).order_by(RagDocument.id).all()
            failed_id, success_id = docs[0].id, docs[1].id
        self.repo.backfill_fingerprint(failed_id, self.hash, "host")
        result = self.repo.backfill_fingerprint(success_id, self.hash, "host")
        self.assertEqual(result["canonicalDocumentId"], success_id)
        self.assertEqual(result["copies"], 2)
        self.assertEqual(
            self.repo.backfill_fingerprint(success_id, self.hash, "host"), result
        )
        with patch.object(self.repo, "delete_documents_by_backend_id") as delete_chunks:
            self.assertIsNone(self.repo.delete_rag_document(success_id))
            delete_chunks.assert_called_once_with(success_id)
        self.assertEqual(self.repo.find_fingerprint("host", self.hash), failed_id)
        with patch.object(self.repo, "delete_documents_by_backend_id"):
            self.assertEqual(self.repo.delete_rag_document(failed_id), "legacy/shared.pdf")
        self.assertIsNone(self.repo.find_fingerprint("host", self.hash))

    def test_department_and_role_access(self):
        restricted = {
            "access_scope": "Restricted",
            "allowed_roles": ["Finance"],
            "owner_department": "A, B",
        }
        self.assertTrue(can_read(restricted, "Finance", "a"))
        self.assertFalse(can_read(restricted, "Finance", "C"))
        self.assertFalse(can_read(restricted, "Staff", "A"))
        self.assertTrue(can_read(restricted, "Admin", "C"))

    def test_script_force_cannot_bypass_duplicate_or_failed_registration(self):
        import requests

        from scripts.upload_documents import batch_upload_with_metadata

        for duplicate in (True, False):
            with (
                self.subTest(duplicate=duplicate),
                tempfile.TemporaryDirectory() as folder,
            ):
                (Path(folder) / "source.txt").write_text("script document")
                calls = []

                class ScriptSession:
                    def __init__(self, mode, recorded_calls):
                        self.headers = {}
                        self.duplicate = mode
                        self.calls = recorded_calls

                    def post(self, url, **kwargs):
                        self.calls.append(url)
                        response = requests.Response()
                        if url.endswith("/duplicate-check"):
                            response.status_code = 200
                            response._content = json.dumps(
                                {
                                    "results": [
                                        {
                                            "status": "DUPLICATE"
                                            if self.duplicate
                                            else "NEW"
                                        }
                                    ]
                                }
                            ).encode()
                        else:
                            response.status_code = 500
                            response._content = b'{"message":"registration failed"}'
                        return response

                with (
                    patch.object(
                        sys,
                        "argv",
                        ["upload_documents.py", "--folder", folder, "--force"],
                    ),
                    patch.object(
                        requests,
                        "Session",
                        return_value=ScriptSession(duplicate, calls),
                    ),
                    redirect_stdout(io.StringIO()),
                ):
                    result = batch_upload_with_metadata()
                self.assertEqual(result, 0 if duplicate else 1)
                self.assertFalse(any(url.endswith("/upload") for url in calls))
                self.assertEqual(len(calls), 1 if duplicate else 2)

    def test_python_storage_backfill_and_retry_use_saved_source(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.modules.document.api.v1.endpoints import router
        from app.modules.document.service import DocumentService
        from app.routers.dependencies import get_document_service

        app = FastAPI()
        app.include_router(router, prefix="/documents")
        app.dependency_overrides[get_document_service] = lambda: DocumentService(
            self.repo, None
        )
        client = TestClient(app)
        admin = {"X-Tenant-Scope": "host", "X-User-Roles": "Admin"}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "script.pdf"
            source.write_bytes(b"document contents")
            doc_id = self.repo.create_rag_document(
                document_name="script",
                file_name="script.pdf",
                file_path=str(source),
                file_size=17,
                access_scope="Restricted",
                allowed_roles=["Finance"],
            )
            result = client.get(
                f"/documents/{doc_id}/source-fingerprint", headers=admin
            )
            self.assertEqual(result.json()["sha256"], self.hash)
            self.assertIsNone(self.repo.get_rag_document(doc_id)["file_sha256"])
            self.assertEqual(
                client.put(
                    f"/documents/{doc_id}/fingerprint",
                    headers=admin,
                    json={"sha256": self.hash},
                ).status_code,
                200,
            )
            before = self.repo.get_rag_document(doc_id)
            self.repo.update_rag_document_status(
                doc_id, "Failed", 0, attempt_id=before["current_ingestion_attempt_id"]
            )
            retry_url = f"/documents/{doc_id}/retry-stored-source"
            self.assertEqual(
                client.post(
                    retry_url, headers={**admin, "X-User-Roles": "Staff"}
                ).status_code,
                404,
            )
            source.write_bytes(b"changed bytes")
            self.assertEqual(
                client.post(retry_url, headers=admin).json()["detail"]["code"],
                "SOURCE_CHANGED",
            )
            source.unlink()
            self.assertEqual(
                client.post(retry_url, headers=admin).json()["detail"]["code"],
                "SOURCE_MISSING",
            )
            self.assertEqual(
                self.repo.get_rag_document(doc_id)["current_ingestion_attempt_id"],
                before["current_ingestion_attempt_id"],
            )
            source.write_bytes(b"document contents")
            calls = []

            def ingest(**kwargs):
                calls.append(kwargs)
                self.assertEqual(
                    Path(kwargs["temp_path"]).read_bytes(), b"document contents"
                )
                self.assertEqual(kwargs["metadata"]["allowedRoles"], ["Finance"])
                Path(kwargs["temp_path"]).unlink()

            with patch(
                "app.modules.document.api.v1.endpoints.IngestionPipeline.run_sync",
                side_effect=ingest,
            ):
                accepted = client.post(retry_url, headers=admin)
                self.assertEqual(accepted.status_code, 200)
                self.assertEqual(accepted.json()["documentId"], doc_id)
                self.assertEqual(client.post(retry_url, headers=admin).status_code, 409)
            self.assertEqual(len(calls), 1)
            after = self.repo.get_rag_document(doc_id)
            self.assertNotEqual(
                after["current_ingestion_attempt_id"],
                before["current_ingestion_attempt_id"],
            )
            self.assertEqual(after["allowed_roles"], before["allowed_roles"])
            self.assertEqual(after["document_name"], before["document_name"])

    def test_api_admission_redaction_validation_and_stale_callbacks(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.modules.document.api.v1.endpoints import router
        from app.modules.document.service import DocumentService
        from app.routers.dependencies import get_document_service

        app = FastAPI()
        app.include_router(router, prefix="/documents")
        app.dependency_overrides[get_document_service] = lambda: DocumentService(
            self.repo, None
        )
        client = TestClient(app)
        admin = {"X-Tenant-Scope": "host", "X-User-Roles": "Admin"}
        payload = {
            "document_name": "original",
            "file_name": "a.pdf",
            "file_path": "uploads/a.pdf",
            "file_size": 17,
            "file_sha256": self.hash,
            "access_scope": "Restricted",
            "allowed_roles": ["Finance"],
            "tenant_id": 99,
        }
        registered = client.post("/documents", json=payload, headers=admin)
        self.assertEqual(registered.status_code, 201)
        doc_id, attempt = registered.json()["id"], registered.json()["attemptId"]
        self.assertIsNone(self.repo.get_rag_document(doc_id)["tenant_id"])
        hidden = client.post(
            "/documents",
            json=payload,
            headers={"X-Tenant-Scope": "host", "X-User-Roles": "Staff"},
        )
        self.assertEqual(hidden.status_code, 409)
        self.assertNotIn("documentId", hidden.json())
        self.assertEqual(hidden.json()["code"], "DUPLICATE")
        with self.session() as db:
            db.query(RagDocument).filter(RagDocument.id == doc_id).update(
                {RagDocument.uploaded_by: "17"}
            )
            db.commit()
        owner = {"X-Tenant-Scope": "host", "X-User-Roles": "Staff", "X-User-Id": "17"}
        owned_status = client.get(
            f"/documents/{doc_id}/ingestion-status", headers=owner
        )
        self.assertEqual(owned_status.status_code, 200)
        self.assertNotIn("file_path", owned_status.json())
        self.assertNotIn("document_name", owned_status.json())
        self.assertFalse(owned_status.json()["canRetry"])
        self.assertEqual(
            client.get(
                f"/documents/{doc_id}/ingestion-status",
                headers={**owner, "X-User-Id": "18"},
            ).status_code,
            404,
        )

        self.assertEqual(
            client.get(
                f"/documents/{doc_id}", headers={"X-User-Roles": "Staff"}
            ).status_code,
            404,
        )
        self.assertEqual(
            client.get(
                f"/documents/{doc_id}",
                headers={"X-Tenant-Scope": "tenant:1", "X-User-Roles": "Admin"},
            ).status_code,
            404,
        )
        self.assertEqual(
            client.post(
                "/documents", json={**payload, "file_sha256": None}, headers=admin
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                "/documents/duplicate-check",
                json={"files": [self.request("a").model_dump()] * 101},
                headers=admin,
            ).status_code,
            422,
        )
        import json

        metadata = json.dumps(
            {
                "backend_document_id": doc_id,
                "attemptId": attempt,
                "accessScope": "Public",
                "allowedRoles": ["Injected"],
            }
        )

        def consume(**kwargs):
            os.remove(kwargs["temp_path"])

        with patch(
            "app.modules.document.api.v1.endpoints.IngestionPipeline.run_sync",
            side_effect=consume,
        ) as pipeline:
            upload = client.post(
                "/documents/upload",
                files={"file": ("renamed.pdf", b"document contents")},
                data={"metadata": metadata},
                headers=admin,
            )
            repeated = client.post(
                "/documents/upload",
                files={"file": ("renamed.pdf", b"document contents")},
                data={"metadata": metadata},
                headers=admin,
            )
            self.assertEqual(upload.status_code, 202)
            self.assertEqual(repeated.status_code, 202)
            self.assertEqual(upload.json()["task_id"], repeated.json()["task_id"])
            pipeline.assert_called_once()
            actual = pipeline.call_args.kwargs["metadata"]
            self.assertEqual(actual["accessScope"], "Restricted")
            self.assertEqual(actual["allowedRoles"], ["Finance"])
            mismatch = client.post(
                "/documents/upload",
                files={"file": ("renamed.pdf", b"wrong bytes")},
                data={"metadata": metadata},
                headers=admin,
            )
            self.assertEqual(mismatch.status_code, 409)
            unregistered = client.post(
                "/documents/upload",
                files={"file": ("renamed.pdf", b"document contents")},
                data={"metadata": "{}"},
                headers=admin,
            )
            self.assertEqual(unregistered.status_code, 400)
        task = client.get(
            "/documents/upload-status/" + upload.json()["task_id"], headers=admin
        )
        self.assertEqual(task.status_code, 200)
        self.repo.update_rag_document_status(doc_id, "Failed", 0, attempt_id=attempt)
        retry = client.post(
            f"/documents/{doc_id}/retry-attempt",
            json={"sha256": self.hash},
            headers=admin,
        )
        self.assertEqual(retry.status_code, 200)
        denied = client.post(
            f"/documents/{doc_id}/retry-attempt",
            json={"sha256": self.hash},
            headers=admin,
        )
        self.assertEqual(denied.status_code, 409)
        stale = client.put(
            f"/documents/{doc_id}/status",
            json={"status": "Completed", "chunk_count": 8, "attempt_id": attempt},
            headers=admin,
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.repo.get_rag_document(doc_id)["ingest_status"], "Pending")

    def test_sql_server_repeatable_upgrade_of_legacy_tables(self):
        if not self.sql_server:
            self.skipTest("SQL Server migration integration")
        schema = self.schema + "_migration"
        script = (
            (
                Path(__file__).resolve().parents[1]
                / "infra/docker/document-fingerprints.sql"
            )
            .read_text()
            .replace("dbo.", schema + ".")
        )
        try:
            with self.original_engine.begin() as c:
                c.execute(text(f"CREATE SCHEMA [{schema}]"))
                c.execute(
                    text(f"CREATE TABLE [{schema}].RagDocuments (Id INT PRIMARY KEY)")
                )
                c.execute(
                    text(
                        f"CREATE TABLE [{schema}].IngestionTasks (Id INT PRIMARY KEY, BackendDocumentId INT)"
                    )
                )
            for _ in range(2):
                with self.original_engine.begin() as c:
                    for batch in script.split("\nGO\n"):
                        c.exec_driver_sql(batch)
            with self.original_engine.connect() as c:
                self.assertEqual(
                    c.execute(
                        text(f"SELECT COL_LENGTH('{schema}.RagDocuments','FileSha256')")
                    ).scalar(),
                    64,
                )
                self.assertEqual(
                    c.execute(
                        text(
                            f"SELECT COL_LENGTH('{schema}.RagDocuments','CurrentIngestionAttemptId')"
                        )
                    ).scalar(),
                    36,
                )
                self.assertEqual(
                    c.execute(
                        text(
                            f"SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID('{schema}.IngestionTasks') AND name='UX_IngestionTasks_DocumentAttempt'"
                        )
                    ).scalar(),
                    1,
                )
        finally:
            with self.original_engine.begin() as c:
                for name in (
                    "RagDocumentFingerprints",
                    "IngestionTasks",
                    "RagDocuments",
                ):
                    c.exec_driver_sql(f"DROP TABLE IF EXISTS [{schema}].[{name}]")
                c.exec_driver_sql(f"DROP SCHEMA [{schema}]")

    def test_sql_server_vector_replacement_is_atomic_and_fenced(self):
        if not self.sql_server:
            self.skipTest("SQL Server VECTOR integration")
        import re
        from types import SimpleNamespace

        schema = self.schema
        original_engine = self.original_engine

        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def __enter__(self):
                self.cursor.__enter__()
                return self

            def __exit__(self, *args):
                return self.cursor.__exit__(*args)

            def execute(self, sql, *args):
                # Production SQL is unchanged. Redirect ONLY its table identifiers
                # inside the isolated test connection, never towards dbo.
                for name in ("RagDocuments", "Documents"):
                    sql = re.sub(r"\b" + name + r"\b", f"[{schema}].[{name}]", sql)
                return self.cursor.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self.cursor, name)

        class Connection:
            def __init__(self):
                self.connection = original_engine.raw_connection()

            def cursor(self):
                return Cursor(self.connection.cursor())

            def __getattr__(self, name):
                return getattr(self.connection, name)

        try:
            with original_engine.begin() as c:
                c.exec_driver_sql(
                    f"CREATE TABLE [{schema}].Documents (id VARCHAR(255) PRIMARY KEY, document NVARCHAR(MAX), metadata NVARCHAR(MAX), embedding VECTOR(1024))"
                )
            doc = self.create("shared.pdf")
            other = self.create("shared.pdf", digest="f" * 64)
            attempt = self.repo.get_rag_document(doc)["current_ingestion_attempt_id"]
            other_attempt = self.repo.get_rag_document(other)[
                "current_ingestion_attempt_id"
            ]
            self.repo.accept_ingestion(doc, attempt, self.hash, "host", "shared.pdf")
            self.repo.accept_ingestion(
                other, other_attempt, "f" * 64, "host", "shared.pdf"
            )

            def store(doc_id, attempt_id, names, vectors=None):
                self.repo.upsert_documents(
                    ids=names,
                    documents=names,
                    metadatas=[
                        {"backend_document_id": doc_id, "source": "shared.pdf"}
                        for _ in names
                    ],
                    embeddings=vectors or [[0.1] * 1024 for _ in names],
                    backend_document_id=doc_id,
                    attempt_id=attempt_id,
                )

            def ids():
                with original_engine.connect() as c:
                    return set(
                        c.exec_driver_sql(
                            f"SELECT id FROM [{schema}].Documents"
                        ).scalars()
                    )

            with patch.object(
                repository, "engine", SimpleNamespace(raw_connection=Connection)
            ):
                store(doc, attempt, ["old1", "old2"])
                store(other, other_attempt, ["other"])
                with self.assertRaises(pyodbc.Error):
                    store(
                        doc,
                        attempt,
                        ["partial1", "invalid2"],
                        [[0.1] * 1024, [0.1] * 3],
                    )
                self.assertEqual(ids(), {"old1", "old2", "other"})
                self.repo.update_rag_document_status(
                    doc, "Failed", 0, attempt_id=attempt
                )
                retry = self.repo.begin_retry(doc, "host", self.hash)
                with self.assertRaises(DocumentConflict):
                    store(doc, attempt, ["stale"])
                self.assertEqual(ids(), {"old1", "old2", "other"})
                self.repo.accept_ingestion(doc, retry, self.hash, "host", "shared.pdf")
                store(doc, retry, ["replacement"])
                self.assertEqual(ids(), {"replacement", "other"})
        finally:
            with original_engine.begin() as c:
                c.exec_driver_sql(f"DROP TABLE IF EXISTS [{schema}].Documents")

    def test_sql_server_concurrent_registration_admission_and_retry(self):
        if not self.sql_server:
            self.skipTest(
                "Set BV_RUN_SQLSERVER_TESTS=1 for actual independent SQL Server connections"
            )
        barrier = threading.Barrier(2)

        def create():
            barrier.wait()
            try:
                return self.create()
            except DocumentConflict:
                return None

        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(lambda _: create(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        doc = next(r for r in results if r is not None)
        attempt = self.repo.get_rag_document(doc)["current_ingestion_attempt_id"]
        barrier = threading.Barrier(2)

        def admit():
            barrier.wait()
            return self.repo.accept_ingestion(
                doc, attempt, self.hash, "host", "test.pdf"
            )

        with ThreadPoolExecutor(2) as workers:
            admissions = list(workers.map(lambda _: admit(), range(2)))
        self.assertEqual(sum(admitted for _, admitted in admissions), 1)
        self.assertEqual(admissions[0][0], admissions[1][0])
        self.repo.update_rag_document_status(doc, "Failed", 0, attempt_id=attempt)
        barrier = threading.Barrier(2)

        def retry():
            barrier.wait()
            try:
                return self.repo.begin_retry(doc, "host", self.hash)
            except DocumentConflict:
                return None

        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(lambda _: retry(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        with self.session() as db:
            self.assertEqual(db.query(RagDocument).count(), 1)
            self.assertEqual(db.query(RagDocumentFingerprint).count(), 1)
            self.assertEqual(db.query(IngestionTask).count(), 1)


if __name__ == "__main__":
    unittest.main()
