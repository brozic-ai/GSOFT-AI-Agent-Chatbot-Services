import os
from functools import lru_cache
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ for SDKs such as LangSmith that read process variables directly.
load_dotenv(override=True)


# Tự động nạp file .env vào os.environ cho LangChain Tracer

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Core Application ---
    ENVIRONMENT: str = "local"
    PROJECT_NAME: str = "Chatbot BVBank AI Service"
    API_V1_STR: str = "/api/v1"

    # API Key để xác thực request nội bộ (rỗng = tắt auth, dùng cho dev mode)
    REQUIRED_API_KEY: str = ""

    # CORS Origins (Hỗ trợ string phân cách bằng phẩy hoặc list)
    BACKEND_CORS_ORIGINS: list[str] | str = [
        "http://localhost",
        "http://localhost:4200",
        "http://172.26.16.1:4200",
        "http://172.26.16.1:5000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # --- Database Config ---
    SQLSERVER_CONNECTIONSTRING: str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        "Server=LAPTOP-BE44K422\\MSSQLSERVER01;Database=gAMSPro_BVB_AI_V1_LIVE_04082026_1;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    # --- AI Provider Config ---
    AI_PROVIDER: str = "vllm"  # Lựa chọn: gemini | vllm | openai_compat
    FALLBACK_AI_PROVIDER: str | None = None
    TEST_PROVIDER: str = "vllm"

    # --- Local / vLLM API Config ---
    LLM_MODEL: str = "qwen2.5:3b"
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    LLM_API_KEY: str = "ollama"

    # --- Gemini API Config ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com"

    # --- OpenAI API Config ---
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- RAG & Vector Database Config ---
    TEI_URL: str = "http://localhost:8080"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMS: int = 1024
    ENABLE_LOCAL_EMBEDDING_FALLBACK: bool = False
    SEARCH_CHAT_TOP_K: int = 5
    SEARCH_TOP_K_MAX: int = 50
    SEARCH_VECTOR_CANDIDATE_COUNT: int = 200
    SEARCH_RRF_CONSTANT: int = 60
    INGESTION_ENABLE_OCR: bool = True
    INGESTION_TESSDATA_PATH: str = "tessdata"
    RAG_CHUNK_SIZE: int = 600
    RAG_CHUNK_OVERLAP: int = 120
    INGESTION_ENABLE_VISION_OCR: bool = False
    RERANKER_TYPE: str = "disabled"
    RERANKER_TOP_K: int = 5
    HYBRID_TOP_K_CANDIDATES: int = 20
    CHAT_HISTORY_LIMIT: int = 10

    # --- Full-Text Search (FTS) Config ---
    # Bật/tắt Full-Text Search. Nếu False, fallback về Vector-only search.
    FTS_ENABLED: bool = True
    # Số lượng candidate tối đa mà CONTAINSTABLE trả về trước khi RRF
    FTS_MAX_CANDIDATES: int = 200
    # Trọng số hai luồng trong RRF (tổng khuyến nghị = 1.0)
    RRF_VECTOR_WEIGHT: float = 0.6
    RRF_FTS_WEIGHT: float = 0.4

    # --- RAG Preprocessing & Context Builder Config ---
    RAG_ENABLE_VIETNAMESE_NORMALIZATION: bool = True
    RAG_ENABLE_MARKDOWN_CONVERSION: bool = True
    RAG_CONTEXT_MAX_CHARS: int = 18000
    RAG_CONTEXT_GENERAL_CHUNK_MAX_CHARS: int = 2000
    RAG_CONTEXT_PROCEDURE_CHUNK_MAX_CHARS: int = 5000
    RAG_CONTEXT_IMAGE_CHUNK_MAX_CHARS: int = 1500
    RAG_CONTEXT_NEAR_DUP_LINE_OVERLAP: float = 0.85
    RAG_DYNAMIC_MAX_TOKENS_ENABLED: bool = True

    # --- LangSmith LLMOps Tracing Config ---
    LANGCHAIN_TRACING_V2: str = "true"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "ai-agent-bvbank"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    LANGSMITH_TRACING: str | None = None
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str | None = None
    LANGSMITH_ENDPOINT: str | None = None

    # --- Net Backend URL ---
    NET_BACKEND_URL: str = "http://localhost:5000"


@lru_cache
def get_settings() -> Settings:
    """Trả về Singleton instance của Settings được cache."""
    return Settings()


# Instance cài đặt sẵn cho việc import tiện lợi
settings = get_settings()

# Đồng bộ biến môi trường cho LangChain Tracing / LangSmith SDK
tracing_enabled = (
    (settings.LANGCHAIN_TRACING_V2 and str(settings.LANGCHAIN_TRACING_V2).lower() == "true")
    or (settings.LANGSMITH_TRACING and str(settings.LANGSMITH_TRACING).lower() == "true")
)
api_key = settings.LANGCHAIN_API_KEY or settings.LANGSMITH_API_KEY or os.getenv("LANGCHAIN_API_KEY", "")
project = settings.LANGCHAIN_PROJECT or settings.LANGSMITH_PROJECT or os.getenv("LANGCHAIN_PROJECT", "ai-agent-bvbank")
endpoint = settings.LANGCHAIN_ENDPOINT or settings.LANGSMITH_ENDPOINT or "https://api.smith.langchain.com"

if tracing_enabled:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGSMITH_API_KEY"] = api_key
    if project:
        os.environ["LANGCHAIN_PROJECT"] = project
        os.environ["LANGSMITH_PROJECT"] = project
    if endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint
        os.environ["LANGSMITH_ENDPOINT"] = endpoint
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ.pop("LANGCHAIN_API_KEY", None)
    os.environ.pop("LANGSMITH_API_KEY", None)


