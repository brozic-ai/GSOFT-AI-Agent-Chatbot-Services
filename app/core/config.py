import os
from functools import lru_cache
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    BACKEND_CORS_ORIGINS: Union[List[str], str] = ["http://localhost", "http://localhost:4200"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
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

    TAVILY_API_KEY: str = ""

    # --- RAG & Vector Database Config ---
    TEI_URL: str = "http://localhost:8080"
    EMBEDDING_DIMS: int = 1024
    SEARCH_CHAT_TOP_K: int = 5
    SEARCH_TOP_K_MAX: int = 50
    SEARCH_VECTOR_CANDIDATE_COUNT: int = 200
    SEARCH_RRF_CONSTANT: int = 60
    INGESTION_ENABLE_OCR: bool = True
    INGESTION_TESSDATA_PATH: str = "tessdata"
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 100
    CHAT_HISTORY_LIMIT: int = 10


@lru_cache
def get_settings() -> Settings:
    """Trả về Singleton instance của Settings được cache."""
    return Settings()

# Instance cài đặt sẵn cho việc import tiện lợi
settings = get_settings()
