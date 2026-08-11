import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Tự động nạp file .env vào os.environ cho LangChain Tracer
load_dotenv(override=True)


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
    LLM_MODEL: str = "qwen3.5:0.8b"
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
    SEARCH_CHAT_TOP_K: int = 5
    SEARCH_TOP_K_MAX: int = 50
    SEARCH_VECTOR_CANDIDATE_COUNT: int = 200
    SEARCH_RRF_CONSTANT: int = 60
    INGESTION_ENABLE_OCR: bool = True
    INGESTION_TESSDATA_PATH: str = "tessdata"
    RAG_CHUNK_SIZE: int = 600
    RAG_CHUNK_OVERLAP: int = 120
    CHAT_HISTORY_LIMIT: int = 10

    # --- LangSmith LLMOps Tracing Config ---
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "ai-agent-bvbank"
    LANGCHAIN_ENDPOINT: str = "https://apac.api.smith.langchain.com"


@lru_cache
def get_settings() -> Settings:
    """Trả về Singleton instance của Settings được cache."""
    return Settings()


# Instance cài đặt sẵn cho việc import tiện lợi
settings = get_settings()

# Đồng bộ biến môi trường cho LangChain Tracing / LangSmith
if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_TRACING_V2.lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    if settings.LANGCHAIN_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    if settings.LANGCHAIN_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
