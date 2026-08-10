"""
Script kiểm tra toàn bộ kết nối hệ thống (Health & Connection Checker)
Kiểm tra: Database SQL Server, AI Backend FastAPI, Ollama LLM, Embedding Server.
"""

import sys
from pathlib import Path

import requests

# Thêm root path để import settings từ app.core.config
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.core.config import settings
except ImportError:
    settings = None


def check_all():
    print("============================================================")
    print("🔍 HỆ THỐNG KIỂM TRA KẾT NỐI (SYSTEM CONNECTION CHECKER)")
    print("============================================================\n")

    # ---------------------------------------------------------
    # 1. Kiểm tra kết nối Ollama (LLM & Embeddings)
    # ---------------------------------------------------------
    print("1️⃣ KIỂM TRA OLLAMA SERVER:")
    ollama_base = getattr(
        settings, "LLM_BASE_URL", "http://localhost:11434/v1"
    ).replace("/v1", "")
    try:
        ver_res = requests.get(f"{ollama_base}/api/version", timeout=3)
        if ver_res.status_code == 200:
            version = ver_res.json().get("version", "N/A")
            print(f"   ✅ Ollama đang hoạt động! (Phiên bản: {version})")

            # Kiểm tra danh sách model đã tải
            tags_res = requests.get(f"{ollama_base}/api/tags", timeout=3)
            if tags_res.status_code == 200:
                models = [m["name"] for m in tags_res.json().get("models", [])]
                print(
                    f"   📦 Danh sách models đã tải trong Ollama ({len(models)}): {', '.join(models)}"
                )

                # Test LLM Model
                llm_model = getattr(settings, "LLM_MODEL", "qwen3.5:0.8b")
                if any(llm_model in m for m in models):
                    print(f"   ✅ LLM Model '{llm_model}': Sẵn sàng!")
                else:
                    print(
                        f"   ⚠️ LƯU Ý: Chưa tìm thấy LLM Model '{llm_model}' trong Ollama. Vui lòng chạy: ollama pull {llm_model}"
                    )

                # Test Embedding Model
                embed_model = getattr(settings, "EMBEDDING_MODEL", "bge-m3:latest")
                if any(embed_model in m or "bge-m3" in m for m in models):
                    print(f"   ✅ Embedding Model '{embed_model}': Sẵn sàng!")
                else:
                    print(
                        f"   ⚠️ LƯU Ý: Chưa tìm thấy Embedding Model '{embed_model}'. Vui lòng chạy: ollama pull {embed_model}"
                    )
        else:
            print(f"   ❌ Ollama trả về lỗi: {ver_res.status_code}")
    except Exception as ex:  # noqa: BLE001
        print(f"   ❌ Không thể kết nối tới Ollama ({ollama_base}): {ex}")
        print("   👉 Hãy mở ứng dụng Ollama hoặc gõ 'ollama serve' trên Terminal.")

    print("\n" + "-" * 60 + "\n")

    # ---------------------------------------------------------
    # 2. Kiểm tra kết nối AI Backend Server (FastAPI)
    # ---------------------------------------------------------
    # print("2️⃣ KIỂM TRA AI BACKEND SERVER (FastAPI):")
    # backend_url = "http://localhost:8000"
    # try:
    #     res = requests.get(f"{backend_url}/", timeout=3)
    #     if res.status_code == 200:
    #         data = res.json()
    #         print(f"   ✅ AI Backend đang bật! (Message: '{data.get('message')}')")
    #         print(f"   📄 API Docs: {backend_url}/docs")
    #     else:
    #         print(f"   ❌ Backend trả về HTTP {res.status_code}")
    # except Exception as ex:
    #     print(f"   ❌ Không thể kết nối tới AI Backend ({backend_url}): {ex}")
    #     print("   👉 Vui lòng mở server: uv run uvicorn app.main:app --reload --port 8000")

    # print("\n" + "-" * 60 + "\n")

    # ---------------------------------------------------------
    # 3. Kiểm tra Dịch vụ Vector Embedding (PyTorch GPU / vLLM / Ollama / TEI)
    # ---------------------------------------------------------
    print("3️⃣ KIỂM TRA DỊCH VỤ VECTOR EMBEDDING (PyTorch GPU / Ollama / TEI):")

    # 3a. Kiểm tra PyTorch SentenceTransformer GPU local
    try:
        import torch
        from sentence_transformers import SentenceTransformer  # noqa: F401

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(
            f"   ✅ PyTorch SentenceTransformer sẵn sàng! (Thiết bị: {device.upper()})"
        )
    except ImportError:
        print(
            "   ℹ️ Chưa cài `sentence-transformers` (Hệ thống sẽ dùng HTTP API fallback)."
        )
    except Exception as st_ex:  # noqa: BLE001
        print(f"   ⚠️ Lỗi kiểm tra SentenceTransformer: {st_ex}")

    # 3b. Kiểm tra OpenAI-compatible Embeddings API (vLLM / Ollama)
    raw_embed_model = getattr(settings, "EMBEDDING_MODEL", "bge-m3:latest")
    embed_models_to_try = [raw_embed_model, "bge-m3:latest", "bge-m3", "BAAI/bge-m3"]
    embed_url = f"{ollama_base}/v1/embeddings"

    success_embed = False
    for model_name in list(dict.fromkeys(embed_models_to_try)):
        try:
            embed_res = requests.post(
                embed_url,
                json={"model": model_name, "input": ["Kiểm tra kết nối embedding"]},
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if embed_res.status_code == 200:
                data = embed_res.json()
                vec = data.get("data", [{}])[0].get("embedding", [])
                print("   ✅ Ollama Embedding API hoạt động hoàn hảo!")
                print(
                    f"   📊 Model '{model_name}' tạo vector thành công ({len(vec)} chiều)."
                )
                success_embed = True
                break
        except (requests.RequestException, KeyError, IndexError):
            pass

    if not success_embed:
        print(
            f"   ⚠️ Không thể gọi Ollama Embedding API tại {embed_url} với model '{raw_embed_model}'."
        )

    # 3c. Kiểm tra TEI Server (Tùy chọn)
    tei_url = getattr(settings, "TEI_URL", "http://localhost:8080")
    try:
        tei_res = requests.get(f"{tei_url}/info", timeout=2)
        if tei_res.status_code == 200:
            print(f"   ✅ TEI Server (HuggingFace TEI) cũng đang bật tại {tei_url}!")
    except requests.RequestException:
        print(
            f"   ℹ️ TEI Server tại {tei_url} chưa bật (Hệ thống đang dùng PyTorch GPU / Ollama Embeddings ở trên)."
        )

    print("\n" + "-" * 60 + "\n")

    # ---------------------------------------------------------
    # 4. Kiểm tra CSDL SQL Server
    # ---------------------------------------------------------
    # print("4️⃣ KIỂM TRA CƠ SỞ DỮ LIỆU (SQL Server):")
    # try:
    #     from app.core.database import SessionLocal
    #     from sqlalchemy import text
    #     with SessionLocal() as session:
    #         session.execute(text("SELECT 1"))
    #     print("   ✅ Kết nối CSDL SQL Server thành công!")
    # except Exception as ex:
    #     print(f"   ❌ Lỗi kết nối CSDL SQL Server: {ex}")

    print("\n============================================================")
    print("🏁 TỔNG KẾT KIỂM TRA HOÀN TẤT")
    print("============================================================\n")


if __name__ == "__main__":
    check_all()
