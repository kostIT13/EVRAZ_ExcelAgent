from __future__ import annotations
import hashlib
from typing import List, Optional
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.db.database import async_session_maker
from src.core.db.vector_models import QueryEmbeddingCache
from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient


class Embedder:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        self._dim: int = settings.EMBED_DIMENSION

    async def embed(self, text: str) -> List[float]:
        cached = await self._load_from_cache(text)
        if cached is not None:
            return cached

        vector = await self._llm.embed(text)

        await self._save_to_cache(text, vector)

        return vector

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]

    @staticmethod
    def _hash_query(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    async def _load_from_cache(self, text: str) -> Optional[List[float]]:
        query_hash = self._hash_query(text)
        async with async_session_maker() as session:
            result = await session.execute(
                select(QueryEmbeddingCache).where(
                    QueryEmbeddingCache.query_hash == query_hash
                )
            )
            record = result.scalar_one_or_none()
            if record is not None:
                logger.debug("Embedding cache hit for hash={}", query_hash[:12])
                return list(record.embedding)
        return None

    async def _save_to_cache(self, text: str, vector: List[float]) -> None:
        query_hash = self._hash_query(text)
        async with async_session_maker() as session:
            existing = await session.execute(
                select(QueryEmbeddingCache).where(
                    QueryEmbeddingCache.query_hash == query_hash
                )
            )
            if existing.scalar_one_or_none() is not None:
                return

            record = QueryEmbeddingCache(
                query_hash=query_hash,
                query_text=text,
                embedding=vector,
                model_name=settings.OLLAMA_EMBED_MODEL,
            )
            session.add(record)
            await session.commit()
            logger.debug("Embedding cached for hash={}", query_hash[:12])

    @property
    def dimension(self) -> int:
        return self._dim


def cosine_similarity(a: List[float], b: List[float]) -> float:
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(arr_a)
    norm_b = np.linalg.norm(arr_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))