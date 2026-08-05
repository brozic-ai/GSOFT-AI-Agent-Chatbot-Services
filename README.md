# Dev LLM Service - Enterprise Chatbot System

Dự án `dev_llm_service` là dịch vụ Backend AI Agent xử lý ngôn ngữ tự nhiên (LLM), RAG (Retrieval-Augmented Generation), và đa đại lý (Multi-Agent System) thuộc hệ thống Enterprise Chatbot (BVBank).

---

## 📋 Mục Lục

1. [Kiến Trúc & Công Nghệ](#-kiến-trúc--công-nghệ)
2. [Cấu Trúc Thư Mục](#-cấu-trúc-thư-mục)
3. [Yêu Cầu Hệ Thống](#-yêu-cầu-hệ-thống)
4. [Hướng Dẫn Cài Đặt](#-hướng-dẫn-cài-đặt)
5. [Cấu Hình Môi Trường (.env)](#-cấu-hình-môi-trường-env)
6. [Khởi Chạy Ứng Dụng](#-khởi-chạy-ứng-dụng)
7. [Hướng Dẫn Phát Triển (Coding Guide)](#-hướng-dẫn-phát-triển-coding-guide)
   - [Thêm LLM Provider Mới](#1-thêm-llm-provider-mới)
   - [Tạo Module API Mới](#2-tạo-module-api-mới)
   - [Xây Dựng Agent / Prompt Mới](#3-xây-dựng-agent--prompt-mới)
8. [Kiểm Tra & Đảm Bảo Chất Lượng Code](#-kiểm-tra--đảm-bảo-chất-lượng-code)

---

## 🛠 Kiến Trúc & Công Nghệ

- **Language:** Python >= 3.11
- **Package Manager:** [uv](https://github.com/astral-sh/uv) (Trình quản lý gói cực nhanh cho Python)
- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
- **AI Frameworks:** LangChain, LangGraph, Google GenAI SDK (`google-genai`), vLLM
- **Database:** SQL Server (sử dụng pyodbc / ODBC Driver 18)
- **LLM Observability & Tracing:** LangSmith
- **Code Quality:** Ruff, MyPy, Pytest, Coverage

---

## 📂 Cấu Trúc Thư Mục

```text
dev_llm_service/
├── app/                        # Mã nguồn chính của ứng dụng (Tất cả thư mục đều chứa __init__.py)
│   ├── ai/                     # Hệ thống AI Agents & RAG
│   │   ├── agent/              # Định nghĩa các Agent hệ thống
│   │   │   ├── agentic_rag/    # Agentic RAG (Evaluation, Graph, Memory, Prompts, Tools)
│   │   │   ├── faq/            # FAQ Agent (Evaluation, Graph, Memory, Prompts, Tools)
│   │   │   └── supervisor/     # Supervisor Agent điều phối các agent con (Evaluation, Graph, Memory, Prompts, Tools)
│   │   └── rag/                # Pipeline RAG (Citation, Embedding, Generator, Ingestion, Reranker, Retrieval)
│   ├── core/                   # Cấu hình cốt lõi (Config, Database, Exception, Logging, Middleware, Security, Session)
│   ├── eval/                   # Module đánh giá chất lượng mô hình (Run Eval, Scorer)
│   ├── llmops/                 # Quản lý & Trích xuất LLM Provider
│   │   ├── base.py             # Interface chung (BaseLLMProvider)
│   │   ├── factory.py          # Factory khởi tạo Provider theo biến môi trường
│   │   └── providers/          # Các Provider cụ thể (Gemini, vLLM, Azure OpenAI, ...)
│   ├── modules/                # Đóng gói logic theo nghiệp vụ
│   │   ├── auth/               # Module Xác thực & Phân quyền
│   │   ├── chat/               # Module Chatbot & Lịch sử hội thoại (API v1, Repo, Service)
│   │   ├── document/           # Module Xử lý & Quản lý tài liệu
│   │   └── health/             # Module kiểm tra trạng thái dịch vụ (Health Check)
│   ├── routers/                # API Routers & Middlewares / Dependencies
│   ├── security/               # Xử lý bảo mật & Mã hóa
│   ├── shared/                 # DTO, Enums, Events, Types, Utils dùng chung
│   ├── lifespan.py             # Quản lý vòng đời ứng dụng FastAPI (Startup / Shutdown)
│   └── main.py                 # File khởi tạo ứng dụng FastAPI
├── infra/                      # Cấu hình hạ tầng
│   ├── docker/                 # docker-compose.yml & SQL init script
│   └── k8s/                    # Cấu hình Kubernetes deployment (.gitkeep)
├── notebooks/                  # Jupyter notebooks cho thử nghiệm OCR, RAG, Prompt
├── scripts/                    # Shell scripts hỗ trợ Dev (lint, format, test)
├── .env                        # File biến môi trường (Local config)
├── pyproject.toml              # Khai báo dependency & cấu hình dự án
└── uv.lock                     # Lockfile phiên bản thư viện
```

---

## 💻 Yêu Cầu Hệ Thống

- Python 3.11 trở lên
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`pip install uv` hoặc cài qua script)
- SQL Server Client (ODBC Driver 18 for SQL Server nếu kết nối tới database trực tiếp)

---

## 🚀 Hướng Dẫn Cài Đặt

### 1. Clone repository & chuyển vào thư mục dự án
```bash
cd dev_llm_service
```

### 2. Tự động khởi tạo môi trường ảo và cài đặt thư viện với `uv`
```bash
# Cài đặt tất cả các phụ thuộc trong uv.lock
uv sync
```
*(Nếu muốn dùng `pip` truyền thống, bạn có thể tạo venv bằng `python -m venv .venv` và kích hoạt venv trước khi cài).*

---

## ⚙️ Cấu Hình Môi Trường (.env)

Tạo file `.env` tại thư mục gốc `dev_llm_service/` (hoặc chỉnh sửa file `.env` có sẵn):

```ini
# --- Core Application ---
ENVIRONMENT=local
PROJECT_NAME="Chatbot BVBank"
BACKEND_CORS_ORIGINS=http://localhost,http://localhost:5173

# --- Database ---
SQLSERVER_CONNECTIONSTRING="Driver={ODBC Driver 18 for SQL Server};Server=YOUR_SERVER;Database=YOUR_DB;User Id=sa;Password=YOUR_PASSWORD;TrustServerCertificate=True;"

# --- AI Provider Switch ---
# Lựa chọn provider: gemini | vllm | azure_open_ai
AI_PROVIDER=gemini

# --- Gemini API Config ---
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_BASE=https://generativelanguage.googleapis.com

# --- LangSmith Tracing ---
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=YOUR_LANGSMITH_API_KEY
LANGSMITH_PROJECT=ai-agent-bvbank
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
```

---

## ▶️ Khởi Chạy Ứng Dụng

### 1. Chạy trên môi trường Local Development (Uvicorn Reload)

Dùng lệnh `uv` để chạy trực tiếp:
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Hoặc kích hoạt virtual environment trước:
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\activate
  uvicorn app.main:app --reload --port 8000
  ```
- **Linux/macOS:**
  ```bash
  source .venv/bin/activate
  uvicorn app.main:app --reload --port 8000
  ```

### 2. Chạy dịch vụ Hạ Tầng (Docker Compose)
Để khởi chạy các dịch vụ bổ trợ (như SQL Server CSDL local):
```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

### 3. Kiểm tra Swagger UI / API Docs
Truy cập trình duyệt tại:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## 🏗 Hướng Dẫn Phát Triển (Coding Guide)

### 1. Thêm LLM Provider Mới

Tất cả các mô hình LLM được trừu tượng hóa thông qua interface [BaseLLMProvider](file:///c:/2_Company/GSOFT/Enterprice-Chatbot/Enterprice_Chatbot/dev_llm_service/app/llmops/base.py).

1. Tạo file mới trong `app/llmops/providers/<new_provider>.py`:
   ```python
   from app.llmops.base import BaseLLMProvider

   class NewLLMProvider(BaseLLMProvider):
       def __init__(self, api_key: str, model_name: str = "custom-model"):
           self.api_key = api_key
           self.model_name = model_name

       def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
           # Logic gọi LLM API và trả về chuỗi văn bản
           pass

       def generate_json(self, system_prompt: str, user_prompt: str, schema: dict | None = None) -> dict:
           # Logic gọi LLM ép kiểu phản hồi trả về dạng dict JSON
           pass
   ```
2. Đăng ký Provider mới trong [app/llmops/factory.py](file:///c:/2_Company/GSOFT/Enterprice-Chatbot/Enterprice_Chatbot/dev_llm_service/app/llmops/factory.py):
   ```python
   elif provider_name == "new_provider":
       return NewLLMProvider(api_key=os.getenv("NEW_PROVIDER_API_KEY"))
   ```

### 2. Tạo Module API Mới

Cấu trúc module theo Domain-Driven Design nằm trong `app/modules/<module_name>`:
```text
app/modules/chat/
├── api/
│   └── v1/
│       ├── endpoints.py   # Các router FastAPI
│       └── schemas.py     # Pydantic Request / Response schemas
├── repository.py          # Truy vấn CSDL
└── service.py             # Business Logic
```

Đăng ký router vào [app/main.py](file:///c:/2_Company/GSOFT/Enterprice-Chatbot/Enterprice_Chatbot/dev_llm_service/app/main.py):
```python
from app.modules.chat.api.v1.endpoints import router as chat_router

app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
```

### 3. Xây Dựng Agent / Prompt Mới

Tổ chức trong `app/ai/agent/<agent_type>/`:
- `prompts/registry.py`: Lưu trữ và phân phiên bản System Prompts.
- `graph/`: Định nghĩa luồng làm việc LangGraph (Nodes, Edges, State).
- `tools/`: Các công cụ Agent có thể gọi (Search, DB Query, Document Lookup,...).

---

## 🧪 Kiểm Tra & Đảm Bảo Chất Lượng Code

Hệ thống cung cấp các kịch bản kiểm tra tự động nằm trong thư mục `scripts/`:

- **Tự động định dạng code (Ruff Format & Fix):**
  ```bash
  # Linux/macOS
  ./scripts/format.sh

  # Hoặc lệnh trực tiếp
  uv run ruff check app scripts --fix
  uv run ruff format app scripts
  ```

- **Kiểm tra Linter & Type Check (Mypy + Ruff):**
  ```bash
  # Linux/macOS
  ./scripts/lint.sh

  # Hoặc lệnh trực tiếp
  uv run mypy app
  uv run ruff check app
  uv run ruff format app --check
  ```

- **Chạy Unit Tests & Coverage Report:**
  ```bash
  # Linux/macOS
  ./scripts/test.sh

  # Hoặc lệnh trực tiếp
  uv run coverage run -m pytest tests/
  uv run coverage report
  ```
