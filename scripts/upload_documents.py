"""
Script tự động nạp toàn bộ tài liệu vào hệ thống RAG & CSDL SQL Server.
Tự động đăng ký Metadata + Tách chunk & Embedding với Rich UI.
"""

import json
import os
import sys
from pathlib import Path

import requests

# Thư mục my_documents nằm tại gốc dự án dev_llm_service
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "my_documents"

BASE_URL = "http://localhost:8000/api/v1/documents"
CREATE_DOC_URL = f"{BASE_URL}"
UPLOAD_DOC_URL = f"{BASE_URL}/upload"
LIST_DOCS_URL = f"{BASE_URL}"

DEFAULT_CATEGORY = "Quy trình nội bộ"
DEFAULT_ACCESS_SCOPE = "Public"
DEFAULT_ALLOWED_ROLES = ["Public", "Employee"]


# ── Rich Console (lazy init, fallback nếu chưa cài) ──
_console = None


def _get_console():
    global _console
    if _console is None:
        try:
            from rich.console import Console

            _console = Console()
        except ImportError:
            _console = False
    return _console if _console else None


def _human_size(size_bytes: int) -> str:
    """Chuyển đổi bytes sang dạng dễ đọc (KB, MB, GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_existing_documents() -> dict:
    """Truy vấn CSDL SQL Server qua API để lấy danh sách các tài liệu đã nạp & tách chunk thành công."""
    console = _get_console()
    if console:
        console.print("  🔍 [dim]Đang kiểm tra tài liệu đã có trong CSDL...[/]", end="")
    else:
        print("🔍 Đang kiểm tra tài liệu đã có trong CSDL...", end="", flush=True)

    try:
        res = requests.get(LIST_DOCS_URL, timeout=(3, 30))
        if res.status_code == 200:
            docs = res.json()
            existing = {}
            for doc in docs:
                f_name = doc.get("file_name")
                chunk_cnt = doc.get("chunk_count", 0)
                status = doc.get("ingest_status", "")
                if f_name and (chunk_cnt > 0 or status in ("Completed", "Success")):
                    existing[f_name] = doc
            if console:
                console.print(f" [green]✓ {len(existing)} tài liệu đã tách chunk[/]")
            else:
                print(f" ✅ Tìm thấy {len(existing)} tài liệu đã tách chunk.")
            return existing
        else:
            msg = f" ⚠️ API trả về HTTP {res.status_code}"
            if console:
                console.print(f" [yellow]{msg}[/]")
            else:
                print(msg)
    except requests.exceptions.ConnectionError:
        msg = "\n   ⚠️ Không kết nối được server — kiểm tra server đã khởi động chưa."
        if console:
            console.print(f"[yellow]{msg}[/]")
        else:
            print(msg)
    except requests.exceptions.ReadTimeout:
        msg = "\n   ⚠️ Server không phản hồi sau 30s — tiếp tục mà không kiểm tra CSDL."
        if console:
            console.print(f"[yellow]{msg}[/]")
        else:
            print(msg)
    except Exception as ex:  # noqa: BLE001
        msg = f"\n   ⚠️ Lỗi kiểm tra CSDL: {ex}"
        if console:
            console.print(f"[yellow]{msg}[/]")
        else:
            print(msg)
    return {}


class ProgressFileReader:
    """Wrapper file object đọc file theo chunk byte, cập nhật Rich progress bar hoặc callback."""

    def __init__(self, file_path: str, callback=None):
        self.file_path = file_path
        self.f = open(file_path, "rb")  # noqa: SIM115
        self.callback = callback
        self.file_size = os.path.getsize(file_path)

    def read(self, size: int = -1) -> bytes:
        chunk = self.f.read(size)
        if chunk and self.callback:
            self.callback(len(chunk), self)
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.f.seek(offset, whence)

    def tell(self) -> int:
        return self.f.tell()

    def __len__(self) -> int:
        return self.file_size

    def close(self):
        self.f.close()


def batch_upload_with_metadata():
    console = _get_console()

    if not DOCUMENTS_DIR.exists():
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        if console:
            from rich.panel import Panel

            console.print(
                Panel(
                    f"📁 Đã tạo thư mục: [cyan]{DOCUMENTS_DIR}[/]\n"
                    f"👉 Copy file tài liệu vào thư mục trên rồi chạy lại script!",
                    border_style="yellow",
                )
            )
        else:
            print(f"📁 Đã tạo thư mục: {DOCUMENTS_DIR}")
            print("👉 Vui lòng chép file tài liệu vào rồi chạy lại script!")
        return

    files = [
        f
        for f in os.listdir(DOCUMENTS_DIR)
        if os.path.isfile(os.path.join(DOCUMENTS_DIR, f)) and not f.startswith(".")
    ]

    if not files:
        if console:
            console.print(
                f"[yellow]⚠️ Thư mục '[cyan]{DOCUMENTS_DIR}[/]' đang trống![/]"
            )
        else:
            print(f"⚠️ Thư mục '{DOCUMENTS_DIR}' đang trống!")
        return

    force_reupload = "--force" in sys.argv or "-f" in sys.argv
    existing_docs = get_existing_documents() if not force_reupload else {}

    total_files = len(files)
    total_size = sum(os.path.getsize(os.path.join(DOCUMENTS_DIR, f)) for f in files)
    new_files = [f for f in files if f not in existing_docs]
    skip_files = [f for f in files if f in existing_docs]

    # ── Header Panel ──
    if console:
        from rich.panel import Panel
        from rich.text import Text

        header = Text()
        header.append("📦 Document Upload Pipeline\n", style="bold cyan")
        header.append(f"   Folder: {DOCUMENTS_DIR}\n", style="dim")
        header.append(
            f"   Files : {total_files} ({_human_size(total_size)})", style="dim"
        )
        if skip_files:
            header.append(f"  •  Skip: {len(skip_files)}", style="dim yellow")
        if new_files:
            header.append(f"  •  New: {len(new_files)}", style="dim green")
        if force_reupload:
            header.append("  •  --force", style="bold red")
        console.print(Panel(header, border_style="cyan", padding=(0, 1)))
        console.print()
    else:
        print(f"🚀 Tìm thấy {total_files} file tài liệu.")
        if existing_docs:
            print(f"🔍 CSDL đã có {len(existing_docs)} tài liệu. (--force để nạp lại)")
        print("-" * 80)

    success_count = 0
    skipped_count = 0
    error_count = 0
    results = []  # (filename, status, detail)

    if console:
        _run_with_rich(console, files, existing_docs, results)
    else:
        _run_plain(files, existing_docs, results)

    # Đếm kết quả
    for _, status, _ in results:
        if status == "success":
            success_count += 1
        elif status == "skipped":
            skipped_count += 1
        else:
            error_count += 1

    # ── Summary Panel ──
    if console:
        from rich.panel import Panel
        from rich.text import Text

        summary = Text()
        summary.append("🎉 HOÀN THÀNH\n", style="bold green")
        summary.append("   ✅ Mới nạp: ", style="white")
        summary.append(f"{success_count}", style="bold green")
        summary.append("   ⏭️ Bỏ qua: ", style="white")
        summary.append(f"{skipped_count}", style="bold yellow")
        if error_count > 0:
            summary.append("   ❌ Lỗi: ", style="white")
            summary.append(f"{error_count}", style="bold red")
        summary.append("   📊 Tổng: ", style="white")
        summary.append(f"{total_files}", style="bold cyan")

        border = "green" if error_count == 0 else "yellow"
        console.print()
        console.print(Panel(summary, border_style=border, padding=(0, 1)))
    else:
        print(
            f"\n🎉 HOÀN THÀNH! Mới nạp: {success_count} | Bỏ qua: {skipped_count} | Lỗi: {error_count} | Tổng: {total_files}"
        )


def _run_with_rich(console, files, existing_docs, results):
    """Chạy upload pipeline với Rich progress bar."""
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TransferSpeedColumn,
    )

    total_files = len(files)

    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold]{task.description}"),
        BarColumn(
            bar_width=30,
            style="bright_black",
            complete_style="cyan",
            finished_style="bold green",
        ),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task(
            f"[cyan]📦 Uploading {total_files} documents...",
            total=total_files,
        )

        for index, filename in enumerate(files, start=1):
            file_path = os.path.join(DOCUMENTS_DIR, filename)
            file_size = os.path.getsize(file_path)

            # ── Skip: đã có trong DB ──
            if filename in existing_docs:
                doc_info = existing_docs[filename]
                chunk_cnt = doc_info.get("chunk_count", 0)

                file_task = progress.add_task(
                    f"[dim]⏭️  {filename}",
                    total=file_size,
                )
                progress.update(
                    file_task,
                    completed=file_size,
                    description=f"[yellow]⏭️  {filename} [dim]({chunk_cnt} chunks → Skip)[/]",
                )
                progress.advance(overall_task)
                results.append((filename, "skipped", f"{chunk_cnt} chunks"))
                continue

            # ── New file: upload ──
            file_task = progress.add_task(
                f"[cyan]📄 {filename}",
                total=file_size,
            )

            raw_name, _ = os.path.splitext(filename)
            doc_name = raw_name.replace("_", " ").replace("-", " ").title()

            # 1. Metadata
            progress.update(
                file_task, description=f"[cyan]📝 {filename} [dim]Metadata...[/]"
            )
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
                    backend_id = res_meta.json().get("id", 0)
                else:
                    console.print(f"   [yellow]⚠️ Metadata lỗi: {res_meta.text}[/]")
            except Exception as ex:
                console.print(f"   [yellow]⚠️ Lỗi kết nối metadata: {ex}[/]")

            # 2. Upload file + embedding
            progress.update(
                file_task,
                description=f"[cyan]📤 {filename} [dim]Gửi byte file...[/]",
            )
            custom_metadata = {
                "backend_id": str(backend_id),
                "backend_document_id": backend_id,
                "accessScope": DEFAULT_ACCESS_SCOPE,
                "allowedRoles": DEFAULT_ALLOWED_ROLES,
                "category": DEFAULT_CATEGORY,
            }

            def _on_read(
                n_bytes, reader_obj, _task=file_task, _total=file_size, _fname=filename
            ):
                progress.advance(_task, n_bytes)
                if reader_obj is not None and reader_obj.tell() >= _total:
                    progress.update(
                        _task,
                        description=f"[bold yellow]⚙️ {_fname} [dim](Tách chunk & Embedding GPU...)[/]",
                    )

            reader = ProgressFileReader(file_path, callback=_on_read)
            try:
                try:
                    upload_res = requests.post(
                        UPLOAD_DOC_URL,
                        files={"file": (filename, reader)},
                        data={
                            "metadata": json.dumps(custom_metadata, ensure_ascii=False)
                        },
                    )
                finally:
                    reader.close()

                if upload_res.status_code == 200:
                    data = upload_res.json()
                    chunk_count = data.get("chunkCount", 0)
                    progress.update(
                        file_task,
                        completed=file_size,
                        description=f"[bold green]✅ {filename} [dim]({chunk_count} chunks thành công)[/]",
                    )
                    results.append((filename, "success", f"{chunk_count} chunks"))
                else:
                    progress.update(
                        file_task,
                        completed=file_size,
                        description=f"[red]❌ {filename} [dim]HTTP {upload_res.status_code}[/]",
                    )
                    console.print(
                        f"   [red]❌ Upload lỗi ({upload_res.status_code}): {upload_res.text[:100]}[/]"
                    )
                    results.append(
                        (filename, "error", f"HTTP {upload_res.status_code}")
                    )

            except Exception as ex:  # noqa: BLE001
                progress.update(
                    file_task,
                    completed=file_size,
                    description=f"[red]❌ {filename} [dim]Connection error[/]",
                )
                console.print(f"   [red]❌ Lỗi kết nối: {ex}[/]")
                results.append((filename, "error", str(ex)[:80]))

            progress.advance(overall_task)


def _run_plain(files, existing_docs, results):
    """Fallback: chạy upload pipeline không có Rich (plain text)."""
    total_files = len(files)

    for index, filename in enumerate(files, start=1):
        file_path = os.path.join(DOCUMENTS_DIR, filename)
        file_size = os.path.getsize(file_path)

        if filename in existing_docs:
            doc_info = existing_docs[filename]
            chunk_cnt = doc_info.get("chunk_count", 0)
            print(
                f"[{index}/{total_files}] ⏭️ {filename}: Đã có ({chunk_cnt} chunks) → Skip"
            )
            results.append((filename, "skipped", f"{chunk_cnt} chunks"))
            continue

        raw_name, _ = os.path.splitext(filename)
        doc_name = raw_name.replace("_", " ").replace("-", " ").title()

        print(
            f"[{index}/{total_files}] 📤 {filename} ({_human_size(file_size)})...",
            end="",
            flush=True,
        )

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
                backend_id = res_meta.json().get("id", 0)
        except Exception as ex:  # noqa: BLE001
            print(f" ⚠️ Metadata error: {ex}")

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
                print(f" ✅ ({chunk_count} chunks)")
                results.append((filename, "success", f"{chunk_count} chunks"))
            else:
                print(f" ❌ HTTP {upload_res.status_code}")
                results.append((filename, "error", f"HTTP {upload_res.status_code}"))
        except Exception as ex:  # noqa: BLE001
            print(f" ❌ {ex}")
            results.append((filename, "error", str(ex)[:80]))


if __name__ == "__main__":
    batch_upload_with_metadata()
