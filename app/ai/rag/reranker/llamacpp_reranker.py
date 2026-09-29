"""
Reranker gọi llama.cpp server (GGUF reranker, vd BGE-Reranker-v2-M3) qua HTTP: POST {RERANKER_URL}/v1/rerank.
"""

import logging
import math

import httpx

from app.ai.rag.reranker.base import BaseReranker

logger = logging.getLogger(__name__)


class LlamaCppReranker(BaseReranker):
    def __init__(self, base_url: str, model: str | None = None) -> None:
        self.rerank_url = f"{base_url.rstrip('/')}/v1/rerank"
        self.model = model or getattr(settings, "RERANKER_MODEL", "BGE-Reranker-v2-M3-Q4_K_M")
        self._client = httpx.Client(timeout=30.0)

    def rerank_with_scores(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        if not chunks:
            return []

        if not query or not query.strip():
            return [(idx, 0.0) for idx in range(min(top_k, len(chunks)))]

        try:
            payload = {"query": query, "documents": chunks, "top_n": top_k}
            if self.model:
                payload["model"] = self.model
            response = self._client.post(
                self.rerank_url,
                json=payload,
            )
            response.raise_for_status()
            # llama.cpp trả raw logit -> sigmoid về 0..1 để khớp RERANKER_SCORE_THRESHOLD
            results = [
                (int(r["index"]), 1.0 / (1.0 + math.exp(-float(r["relevance_score"]))))
                for r in response.json()["results"]
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
        except Exception as ex:  # noqa: BLE001
            logger.warning("[RERANKER] Lỗi gọi llama.cpp rerank (%s). Fallback về thứ tự gốc.", ex)
            return [(idx, 1.0 / (1.0 + idx)) for idx in range(min(top_k, len(chunks)))]

    def rerank(
        self,
        query: str,
        chunks: list[str],
        top_k: int,
    ) -> list[int]:
        return [idx for idx, _ in self.rerank_with_scores(query, chunks, top_k)]
