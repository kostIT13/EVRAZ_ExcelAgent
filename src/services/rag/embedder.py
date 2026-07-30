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


MAX_EMBED_CHARS = 18000


def _truncate_text_for_embed(text: str, max_chars: int = MAX_EMBED_CHARS) -> str:
    """Обрезает текст до безопасного лимита для модели эмбеддинга.
    
    Модель BAAI/bge-m3 имеет контекст 8192 токенов.
    Обрезаем по границе абзаца или предложения, чтобы сохранить смысл.
    """
    if len(text) <= max_chars:
        return text
    # Пробуем обрезать по границе абзаца
    truncated = text[:max_chars]
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars // 2:
        result = text[:last_para]
        logger.warning("Text truncated for embedding from {} to {} chars (by paragraph)", len(text), len(result))
        return result
    # Пробуем обрезать по границе предложения
    last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
    if last_sentence > max_chars // 2:
        result = text[:last_sentence + 1]
        logger.warning("Text truncated for embedding from {} to {} chars (by sentence)", len(text), len(result))
        return result
    # Обрезаем по границе слова
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        result = text[:last_space]
        logger.warning("Text truncated for embedding from {} to {} chars (by word)", len(text), len(result))
        return result
    logger.warning("Text truncated for embedding from {} to {} chars (hard cut)", len(text), len(truncated))
    return truncated


class Embedder:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        self._dim: int = settings.EMBED_DIMENSION

    async def embed(self, text: str) -> List[float]:
        # Обрезаем текст до безопасного лимита модели
        safe_text = _truncate_text_for_embed(text)
        
        cached = await self._load_from_cache(safe_text)
        if cached is not None:
            return cached

        vector = await self._llm.embed(safe_text)

        await self._save_to_cache(safe_text, vector)

        return vector

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Обрезаем каждый текст перед эмбеддингом
        safe_texts = [_truncate_text_for_embed(t) for t in texts]
        return [await self.embed(t) for t in safe_texts]

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