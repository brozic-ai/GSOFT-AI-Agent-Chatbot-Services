"""
Dịch vụ Embedding Service (Hỗ trợ SentenceTransformers PyTorch GPU / TEI / vLLM / Ollama).

Đóng vai trò quản lý mô hình BAAI/bge-m3 (1024 chiều):
- Ưu tiên 1: Chạy trực tiếp PyTorch GPU CUDA bằng `SentenceTransformer("BAAI/bge-m3", device="cuda")`
- Ưu tiên 2: Kết nối TEI HTTP Server (http://localhost:8080)
- Ưu tiên 3: Kết nối OpenAI-compatible Embedding API (vLLM / Ollama /v1/embeddings)
"""

import logging

import httpx
from cachetools import TTLCache

from app.core.config import settings

logger = logging.getLogger(__name__)

# LRU Cache cho Query Embeddings (tối đa 1,024 câu truy vấn, TTL 1 giờ)
_QUERY_EMBEDDING_CACHE: TTLCache = TTLCache(maxsize=1024, ttl=3600)

_LOCAL_TRANSFORMER_MODEL = None


def get_local_transformer_model():
    """Tải và cache mô hình SentenceTransformer trên GPU (CUDA) nếu khả thi."""
    global _LOCAL_TRANSFORMER_MODEL
    if _LOCAL_TRANSFORMER_MODEL is None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            raw_model_name = getattr(settings, "EMBEDDING_MODEL", "BAAI/bge-m3")

            # Map tên Ollama format (bge-m3:latest) → HuggingFace format (BAAI/bge-m3)
            # SentenceTransformer chỉ chấp nhận HuggingFace model ID (không có dấu ':')
            _OLLAMA_TO_HF_MAP = {
                "bge-m3:latest": "BAAI/bge-m3",
                "bge-m3": "BAAI/bge-m3",
            }
            model_name = _OLLAMA_TO_HF_MAP.get(raw_model_name, raw_model_name)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                "Initializing SentenceTransformer('%s') on device='%s'...",
                model_name,
                device,
            )
            try:
                _LOCAL_TRANSFORMER_MODEL = SentenceTransformer(
                    model_name, device=device
                )
            except Exception as load_err:
                logger.info(
                    "Retrying SentenceTransformer with weights_only=False fallback (%s)...",
                    load_err,
                )
                _LOCAL_TRANSFORMER_MODEL = SentenceTransformer(
                    model_name, device=device, model_kwargs={"weights_only": False}
                )
            logger.info(
                "[OK] SentenceTransformer loaded successfully on device='%s'.", device
            )
        except Exception as ex:
            logger.warning(
                "Could not initialize local SentenceTransformer (%s). Will fallback to HTTP endpoints.",
                ex,
            )
            _LOCAL_TRANSFORMER_MODEL = False  # Đánh dấu không khả dụng
    return _LOCAL_TRANSFORMER_MODEL if _LOCAL_TRANSFORMER_MODEL is not False else None


class TeiEmbeddingService:
    """Service tạo Vector Embeddings hỗ trợ PyTorch GPU, TEI, vLLM & Ollama."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.TEI_URL).rstrip("/")
        self.embed_url = f"{self.base_url}/embed"

    async def embed_texts(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """
        Tạo embeddings cho danh sách đoạn văn bản.
        """
        if not texts:
            return []

        # 1. Thử dùng SentenceTransformer PyTorch GPU trực tiếp nếu được cài đặt
        local_model = get_local_transformer_model()
        if local_model is not None:
            try:
                embeddings = local_model.encode(
                    texts, batch_size=batch_size, show_progress_bar=False
                )
                return embeddings.tolist()
            except Exception as st_ex:
                logger.warning(
                    "PyTorch SentenceTransformer embed failed (%s). Falling back to HTTP APIs...",
                    st_ex,
                )

        all_embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 2. Thử kết nối TEI Server (Text Embeddings Inference)
            try:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    response = await client.post(
                        self.embed_url,
                        json={"inputs": batch},
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                    embeddings = response.json()
                    all_embeddings.extend(embeddings)
                return all_embeddings
            except Exception as tei_ex:
                logger.debug(
                    "[INFO] TEI Server connection failed (%s). Trying OpenAI-compatible (vLLM / Ollama) Embeddings...",
                    tei_ex,
                )

            # 3. Gọi OpenAI-compatible Embeddings API (/v1/embeddings - Tương thích chuẩn với vLLM, Ollama, OpenAI)
            try:
                embed_endpoint = f"{settings.LLM_BASE_URL.rstrip('/')}/embeddings"
                raw_model_name = getattr(settings, "EMBEDDING_MODEL", "bge-m3:latest")
                headers = {"Content-Type": "application/json"}
                if settings.LLM_API_KEY and settings.LLM_API_KEY != "EMPTY":
                    headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

                # Thử các variant tên model (ví dụ "BAAI/bge-m3" trên HuggingFace vs "bge-m3:latest" trên Ollama)
                candidate_models = (
                    [raw_model_name, "bge-m3:latest", "bge-m3"]
                    if "/" in raw_model_name
                    else [raw_model_name]
                )

                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    res_data = None
                    for model_name in candidate_models:
                        try:
                            response = await client.post(
                                embed_endpoint,
                                json={"model": model_name, "input": batch},
                                headers=headers,
                            )
                            response.raise_for_status()
                            res_data = response.json()
                            break
                        except (httpx.HTTPError, KeyError, ValueError):
                            continue

                    if not res_data:
                        raise RuntimeError(
                            f"Could not get embeddings from {embed_endpoint} with models {candidate_models}"
                        )

                    embeddings = [
                        item["embedding"] for item in res_data.get("data", [])
                    ]
                    all_embeddings.extend(embeddings)
                return all_embeddings
            except Exception as vllm_ex:
                logger.error(
                    "[FAIL] Error calling OpenAI-compatible (vLLM/Ollama) Embedding API: %s",
                    vllm_ex,
                    exc_info=True,
                )
                raise vllm_ex

    async def embed_query(self, query: str) -> list[float]:
        """
        Tạo embedding cho 1 câu truy vấn của người dùng.
        """
        res = await self.embed_texts([query])
        if res and len(res) > 0:
            return res[0]
        raise ValueError("Embedding Service returned empty embedding for query.")

    async def embed_query_cached(self, query: str) -> tuple[list[float], bool]:
        """
        Tạo embedding cho câu truy vấn có sử dụng Cache.
        Trả về: (embedding_vector, cache_hit_boolean)
        """
        cache_key = query.strip()
        if cache_key in _QUERY_EMBEDDING_CACHE:
            logger.debug("[CACHE HIT] Query embedding retrieved from cache.")
            return _QUERY_EMBEDDING_CACHE[cache_key], True

        embedding = await self.embed_query(query)
        _QUERY_EMBEDDING_CACHE[cache_key] = embedding
        return embedding, False
