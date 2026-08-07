"""
Script tự động nạp toàn bộ tài liệu vào hệ thống RAG & CSDL SQL Server.
Tự động đăng ký Metadata + Tách chunk & Embedding với thanh tiến trình tqdm.
"""

import os
import json
import requests
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# Thư mục my_documents nằm tại gốc dự án dev_llm_service
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "my_documents"

BASE_URL = "http://localhost:8000/api/v1/document"
CREATE_DOC_URL = f"{BASE_URL}/documents"
UPLOAD_DOC_URL = f"{BASE_URL}/upload"

DEFAULT_CATEGORY = "Quy trình nội bộ"
DEFAULT_ACCESS_SCOPE = "Public"
DEFAULT_ALLOWED_ROLES = ["Public", "Employee"]


def batch_upload_with_metadata():
    if not DOCUMENTS_DIR.exists():
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"📁 Đã tạo thư mục: {DOCUMENTS_DIR}")
        print(f"👉 Vui lòng chép file tài liệu vào thư mục '{DOCUMENTS_DIR}' rồi chạy lại script!")
        return

    files = [
        f for f in os.listdir(DOCUMENTS_DIR)
        if os.path.isfile(os.path.join(DOCUMENTS_DIR, f)) and not f.startswith(".")
    ]

    if not files:
        print(f"⚠️ Thư mục '{DOCUMENTS_DIR}' đang trống! Hãy copy file vào đây trước.")
        return

    print(f"🚀 Tìm thấy {len(files)} file tài liệu. Bắt đầu quy trình nạp & embedding...\n")

    success_count = 0
    total_files = len(files)

    for index, filename in enumerate(files, start=1):
        file_path = os.path.join(DOCUMENTS_DIR, filename)
        file_size = os.path.getsize(file_path)

        raw_name, _ = os.path.splitext(filename)
        doc_name = raw_name.replace("_", " ").replace("-", " ").title()

        # Tạo thanh tiến trình 0% -> 100% riêng biệt cho từng file
        pbar = tqdm(
            total=100,
            desc=f"[{index}/{total_files}] 📄 {filename[:30]} ({file_size / 1024:.1f} KB)",
            unit="%",
            leave=True
        ) if tqdm else None

        # 1. Tạo Metadata trong CSDL SQL Server (0% -> 20%)
        if pbar:
            pbar.set_postfix_str("Đang tạo Metadata SQL...")
            pbar.update(20)

        create_payload = {
            "document_name": doc_name,
            "file_name": filename,
            "file_path": file_path,
            "file_size": file_size,
            "category": DEFAULT_CATEGORY,
            "description": f"Tài liệu {doc_name} được nạp tự động vào hệ thống RAG.",
            "access_scope": DEFAULT_ACCESS_SCOPE,
            "allowed_roles": DEFAULT_ALLOWED_ROLES,
        }

        backend_id = 0
        try:
            res_meta = requests.post(CREATE_DOC_URL, json=create_payload)
            if res_meta.status_code in (200, 201):
                res_json = res_meta.json()
                backend_id = res_json.get("id", 0)
            else:
                if pbar:
                    tqdm.write(f"   ⚠️ Đăng ký metadata thất bại: {res_meta.text}")
        except Exception as ex:
            if pbar:
                tqdm.write(f"   ⚠️ Lỗi kết nối đăng ký metadata: {ex}")

        # 2. Upload file & Tách chunk + Embedding GPU (20% -> 90%)
        if pbar:
            pbar.set_postfix_str("Đang Upload & Embedding GPU...")
            pbar.update(40)

        custom_metadata = {
            "backend_id": str(backend_id),
            "backend_document_id": backend_id,
            "accessScope": DEFAULT_ACCESS_SCOPE,
            "allowedRoles": DEFAULT_ALLOWED_ROLES,
            "category": DEFAULT_CATEGORY,
        }

        try:
            with open(file_path, "rb") as f:
                upload_res = requests.post(
                    UPLOAD_DOC_URL,
                    files={"file": (filename, f)},
                    data={"metadata": json.dumps(custom_metadata, ensure_ascii=False)},
                )

            if upload_res.status_code == 200:
                data = upload_res.json()
                chunk_count = data.get("chunkCount", 0)
                success_count += 1

                if pbar:
                    pbar.set_postfix_str(f"Thành công ({chunk_count} chunks)")
                    pbar.update(40)  # Chạm mốc 100%
                else:
                    print(f"[{index}/{total_files}] ✅ {filename}: Thành công! ({chunk_count} vector chunks)")
            else:
                if pbar:
                    pbar.set_postfix_str("Lỗi Upload")
                    pbar.update(40)
                    tqdm.write(f"   ❌ Lỗi Upload/Embedding ({upload_res.status_code}): {upload_res.text}")
                else:
                    print(f"[{index}/{total_files}] ❌ Lỗi ({upload_res.status_code}): {upload_res.text}")

        except Exception as ex:
            if pbar:
                pbar.set_postfix_str("Lỗi kết nối")
                pbar.update(40)
                tqdm.write(f"   ❌ Lỗi kết nối Upload: {ex}")
            else:
                print(f"[{index}/{total_files}] ❌ Lỗi kết nối Upload: {ex}")

        if pbar:
            pbar.close()

    print(f"\n🎉 HOÀN THÀNH! Đã nạp thành công {success_count}/{total_files} tài liệu.")


if __name__ == "__main__":
    batch_upload_with_metadata()