"""Import files using atomic tenant/SHA-256 registration, then admit one attempt.

--force remains accepted for compatibility but never creates duplicate metadata.
Retry existing failed documents from the management UI using their saved source.
"""

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def batch_upload_with_metadata():
    from app.core.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=PROJECT_ROOT / "my_documents")
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "RAG_DOCUMENT_API_URL", "http://localhost:8000/api/v1/documents"
        ),
    )
    parser.add_argument("--tenant", type=int, default=None)
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Compatibility flag; does not bypass fingerprint checks",
    )
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.tenant is not None and args.tenant <= 0:
        parser.error("--tenant must be positive")
    if not args.folder.is_dir():
        print(f"Create the folder and add documents: {args.folder}")
        return 1
    if args.force:
        print(
            "--force does not bypass duplicate protection. Retry Failed documents in the management UI."
        )
    session = requests.Session()
    session.headers.update(
        {
            "X-Tenant-Scope": "host"
            if args.tenant is None
            else f"tenant:{args.tenant}",
            "X-User-Roles": "Admin",
        }
    )
    api_key = os.getenv("REQUIRED_API_KEY") or getattr(settings, "REQUIRED_API_KEY", "")
    if api_key:
        session.headers["X-Internal-Api-Key"] = api_key
    base = args.base_url.rstrip("/")
    completed = skipped = failed = accepted = 0
    for file in sorted(args.folder.iterdir()):
        if not file.is_file() or file.name.startswith("."):
            continue
        try:
            if (
                file.suffix.lower()
                not in {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt"}
                or not 0 < file.stat().st_size <= 50 * 1024 * 1024
            ):
                raise ValueError("Unsupported extension or size (1 byte to 50 MB)")
            with file.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            check = session.post(
                base + "/duplicate-check",
                json={
                    "files": [
                        {
                            "fileId": file.name,
                            "sha256": digest,
                            "fileSize": file.stat().st_size,
                        }
                    ]
                },
                timeout=(3, 30),
            )
            check.raise_for_status()
            result = check.json()["results"][0]
            if result["status"] != "NEW":
                print(f"SKIP {file.name}: {result['status']}")
                skipped += 1
                continue
            create = session.post(
                base,
                json={
                    "document_name": file.stem,
                    "file_name": file.name,
                    "file_path": str(file.resolve()),
                    "file_size": file.stat().st_size,
                    "file_sha256": digest,
                    "category": "Quy trình nội bộ",
                    "access_scope": "Public",
                    "tenant_id": args.tenant,
                    "allowed_roles": [],
                    "uploaded_by": "ImportScript",
                },
                timeout=(3, 30),
            )
            if create.status_code == 409:
                print(f"SKIP {file.name}: duplicate registered concurrently")
                skipped += 1
                continue
            create.raise_for_status()  # Never ingest with backend_document_id=0 after registration failure.
            registration = create.json()
            doc_id, attempt = registration["id"], registration["attemptId"]
            import json

            with file.open("rb") as source:
                upload = session.post(
                    base + "/upload",
                    files={"file": (file.name, source)},
                    data={
                        "metadata": json.dumps(
                            {"backend_document_id": doc_id, "attemptId": attempt}
                        )
                    },
                    timeout=(3, 300),
                )
            upload.raise_for_status()
            task_id = upload.json()["task_id"]
            deadline = time.monotonic() + args.wait_seconds
            state = "PENDING"
            while time.monotonic() < deadline:
                response = session.get(
                    base + "/upload-status/" + task_id, timeout=(3, 30)
                )
                response.raise_for_status()
                state = response.json()["status"]
                if state in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(3)
            if state == "COMPLETED":
                completed += 1
            elif state == "FAILED":
                failed += 1
            else:
                accepted += 1
            print(f"{state} {file.name}: document={doc_id}, attempt={attempt}")
        except requests.RequestException:
            # Network uncertainty is not proof ingestion failed; operator checks the saved attempt.
            print(
                f"CHECK STATUS {file.name}: request failed; inspect document state before retrying."
            )
            failed += 1
        except (ValueError, OSError, KeyError) as ex:
            print(f"ERROR {file.name}: {ex}")
            failed += 1
    print(
        f"Completed={completed} Accepted/Processing={accepted} Skipped={skipped} Errors={failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(batch_upload_with_metadata())
